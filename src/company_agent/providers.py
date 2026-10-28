from __future__ import annotations

import http.client
import ipaddress
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from company_agent.catalog import (
    contract_snapshot,
    load_providers,
    load_result_policy,
    load_tools,
    verify_snapshot_current,
)
from company_agent.contracts import PROVIDER_PROTOCOL
from company_agent.diagnostics import contract_digest, emit
from company_agent.jsonutil import loads as strict_json_loads
from company_agent.receipts import (
    ReceiptError,
    business_ref_from_result,
    record_dispatch,
    record_outcome,
    requires_dispatch_record,
)
from company_agent.sanitize import has_forbidden_output, short_result, validate_output_content

_MAX_RESPONSE_BYTES = 1_000_000
_ALLOWED_ENDPOINT_SCHEMES = {"http", "https"}
_MAX_RESULT_DEPTH = 12
_MAX_RESULT_COLLECTION_ITEMS = 10_000


def _validate_json_value(value: Any, *, depth: int = 0) -> None:
    if depth > _MAX_RESULT_DEPTH:
        raise ProviderError("provider result exceeds maximum nesting depth")
    if isinstance(value, str):
        if len(value.encode("utf-8")) > 100_000:
            raise ProviderError("provider result contains an oversized string")
        return
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, int):
        if value.bit_length() > 4096:
            raise ProviderError("provider result contains an oversized integer")
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ProviderError("provider result contains a non-finite number")
        if value == 0.0 and math.copysign(1.0, value) < 0:
            raise ProviderError("provider result contains negative zero")
        return
    if isinstance(value, list):
        if len(value) > _MAX_RESULT_COLLECTION_ITEMS:
            raise ProviderError("provider result contains an oversized list")
        for item in value:
            _validate_json_value(item, depth=depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > _MAX_RESULT_COLLECTION_ITEMS:
            raise ProviderError("provider result contains an oversized object")
        for key, item in value.items():
            if not isinstance(key, str):
                raise ProviderError("provider result object keys must be strings")
            if len(key.encode("utf-8")) > 512:
                raise ProviderError("provider result contains an oversized object key")
            _validate_json_value(item, depth=depth + 1)
        return
    raise ProviderError(f"provider result contains unsupported type {type(value).__name__}")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        del req, fp, code, msg, headers, newurl
        return None


_PROXY_HANDLER = urllib.request.ProxyHandler({})
_OPENER = urllib.request.build_opener(_PROXY_HANDLER, _NoRedirect)


def _contains_key(value: Any, key: str, *, _depth: int = 0) -> bool:
    if _depth > 16:
        return False
    if isinstance(value, dict):
        return key in value or any(_contains_key(item, key, _depth=_depth + 1) for item in value.values())
    if isinstance(value, list):
        return any(_contains_key(item, key, _depth=_depth + 1) for item in value)
    return False


class ProviderError(RuntimeError):
    """A provider contract or transport violation, fail-closed by default."""

    decisive: bool = False


def _decisive(message: str) -> ProviderError:
    """Mark an authoritative provider refusal (4xx) as decisive, never unknown."""

    error = ProviderError(message)
    error.decisive = True
    return error


@dataclass(frozen=True)
class ProviderClient:
    id: str
    url_env: str
    expected_provider: str
    timeout: float = 30.0
    token_env: str = ""
    allow_twin_id: bool = False

    def configured(self) -> bool:
        try:
            provider_rows = {str(row["id"]): row for row in load_providers().get("providers") or []}
            contract = provider_rows.get(self.expected_provider)
            if not isinstance(contract, dict):
                return False
            if contract.get("env") != self.url_env or contract.get("token_env", "") != self.token_env:
                return False
            endpoint = bool(self.endpoint())
            token_required = bool(self.token_env)
            token = str(os.environ.get(self.token_env) or "") if self.token_env else ""
            token_present = (
                bool(token.strip()) and "\r" not in token and "\n" not in token and len(token) <= 8192
            )
            return endpoint and (token_present or not token_required)
        except (ProviderError, KeyError, TypeError, ValueError, RuntimeError):
            return False

    def endpoint(self) -> str:
        raw = str(os.environ.get(self.url_env) or "").strip()
        if not raw:
            return ""
        if any(ord(char) < 32 or ord(char) == 127 for char in raw):
            raise ProviderError(f"{self.url_env} contains invalid URL characters")
        parsed = urllib.parse.urlsplit(raw)
        if parsed.scheme != parsed.scheme.casefold():
            raise ProviderError(f"{self.url_env} scheme must be lowercase")
        if parsed.scheme.casefold() not in _ALLOWED_ENDPOINT_SCHEMES or not parsed.hostname:
            raise ProviderError(f"{self.url_env} must be an absolute HTTP(S) URL")
        if parsed.netloc != parsed.netloc.casefold():
            raise ProviderError(f"{self.url_env} authority must be lowercase")
        if parsed.username is not None or parsed.password is not None or parsed.fragment:
            raise ProviderError(f"{self.url_env} contains forbidden URL components")
        try:
            ascii_hostname = parsed.hostname.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise ProviderError(f"{self.url_env} contains an invalid hostname") from exc
        if parsed.hostname != ascii_hostname:
            raise ProviderError(f"{self.url_env} hostname must use ASCII or punycode")
        if parsed.hostname != parsed.hostname.casefold():
            raise ProviderError(f"{self.url_env} hostname must be lowercase")
        if parsed.hostname.endswith("."):
            raise ProviderError(f"{self.url_env} hostname must not end with a dot")
        labels = parsed.hostname.split(".")
        hostname = parsed.hostname.casefold()
        try:
            ipaddress.ip_address(hostname)
            invalid_label = False
        except ValueError:
            invalid_label = any(
                not label or len(label) > 63 or label.startswith("-") or label.endswith("-")
                for label in labels
            )
        if invalid_label:
            raise ProviderError(f"{self.url_env} contains an invalid hostname")
        if len(parsed.hostname) > 253:
            raise ProviderError(f"{self.url_env} hostname is too long")
        if parsed.query:
            raise ProviderError(f"{self.url_env} must not contain a query string")
        if parsed.path in {"", "/"}:
            raise ProviderError(f"{self.url_env} must include an explicit invoke path")
        if parsed.path.endswith("/"):
            raise ProviderError(f"{self.url_env} path must not end with a slash")
        if len(parsed.path) > 2048:
            raise ProviderError(f"{self.url_env} path is too long")
        path_text = urllib.parse.unquote(parsed.path)
        if any(ord(char) < 32 or ord(char) == 127 for char in path_text):
            raise ProviderError(f"{self.url_env} contains invalid path characters")
        if any(segment in {".", ".."} for segment in path_text.split("/")):
            raise ProviderError(f"{self.url_env} contains forbidden path traversal")
        if parsed.path != urllib.parse.quote(path_text, safe="/-._~"):
            raise ProviderError(f"{self.url_env} path must use canonical URL encoding")
        if "//" in parsed.path:
            raise ProviderError(f"{self.url_env} path must not contain empty segments")
        try:
            port = parsed.port
        except ValueError as exc:
            raise ProviderError(f"{self.url_env} contains an invalid port") from exc
        if port is not None and not 1 <= port <= 65535:
            raise ProviderError(f"{self.url_env} contains an invalid port")
        if parsed.scheme == "https" and port == 443:
            raise ProviderError(f"{self.url_env} must omit the default HTTPS port")
        if parsed.scheme == "http" and port == 80:
            raise ProviderError(f"{self.url_env} must omit the default HTTP port")
        hostname = parsed.hostname.casefold()
        try:
            loopback = ipaddress.ip_address(hostname).is_loopback
        except ValueError:
            loopback = hostname == "localhost"
        if parsed.scheme.casefold() == "http" and not loopback:
            raise ProviderError(f"{self.url_env} must use HTTPS for non-loopback endpoints")
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))

    def invoke(self, operation: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        with contract_snapshot():
            return self._invoke_checked(operation, payload)

    def _invoke_checked(self, operation: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        load_result_policy()
        rows = [row for row in load_tools().values() if row["operation"] == operation]
        if len(rows) != 1:
            raise ProviderError("provider operation is invalid")
        row = rows[0]
        event = {
            "version": "1.0", "event": "provider", "tool": row["name"],
            "operation": operation, "request_id": "", "contract_digest": contract_digest(),
            "elapsed_ms": 0, "status": "started", "error_category": "none",
            "execution_state": "not_dispatched",
        }
        start = time.monotonic()

        def stripe() -> int:
            return max(0, int((time.monotonic() - start) * 1000))

        try:
            result = self._invoke(operation, payload, event)
            # Import at call time to share the exact tool postconditions without a module cycle.
            from company_agent.invoke import _validate_handles, _validate_output

            _validate_handles(row["name"], result, payload)
            _validate_output(row["name"], result)
            event.update(status="ok", execution_state="completed", elapsed_ms=stripe())
            # The delivered result is schema-validated at this point, so the
            # contract-declared reference extraction sees only platform facts.
            record_outcome(
                event, refused=False,
                business_ref=business_ref_from_result(operation, result),
            )
            return result
        except Exception as exc:
            event["status"] = "error"
            if event["error_category"] == "none":
                event["error_category"] = "invalid_result" if event["request_id"] else "validation"
            if event["execution_state"] == "dispatched":
                event["elapsed_ms"] = stripe()
                decisive = bool(
                    getattr(exc, "decisive", False)
                    or getattr(getattr(exc, "__cause__", None), "decisive", False)
                ) and event["error_category"] in {"remote", "authentication"}
                if requires_dispatch_record(operation):
                    record_outcome(event, refused=decisive)
                # The request was sent but the outcome was not confirmed: the
                # platform state is genuinely unknown unless the provider
                # answered authoritatively. Persist the locator either way so
                # an operator can reconcile against platform facts.
                event["execution_state"] = "unknown"
                if (
                    requires_dispatch_record(operation)
                    and not decisive
                    and operation in {"device.run", "hpc.submit", "cloud.submit"}
                ):
                    label = "device execution" if operation == "device.run" else operation
                    raise ProviderError(
                        f"{label} outcome unknown; do not retry automatically; "
                        f"request_id={event['request_id']}"
                    ) from exc
            raise
        finally:
            event["elapsed_ms"] = stripe()
            emit(event)

    def _invoke(
        self, operation: str, payload: Mapping[str, Any], event: dict[str, Any],
    ) -> dict[str, Any]:
        # Load result restrictions before any operation can have side effects.
        load_result_policy()
        if not isinstance(operation, str) or not operation or len(operation) > 128:
            raise ProviderError("provider operation is invalid")
        if not isinstance(payload, Mapping) or not isinstance(payload, dict):
            raise ProviderError("provider payload must be a JSON object")
        try:
            provider_rows = {str(row["id"]): row for row in load_providers().get("providers") or []}
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError("provider contract is invalid") from exc
        contract = provider_rows.get(self.expected_provider)
        if not isinstance(contract, dict):
            raise ProviderError(f"provider {self.expected_provider} is not in the provider contract")
        if set(contract) != {"id", "kind", "env", "token_env", "operations"}:
            raise ProviderError(f"provider {self.expected_provider} contract has unknown fields")
        operation_rows = contract.get("operations")
        if not isinstance(operation_rows, list) or len(operation_rows) != len(set(operation_rows)):
            raise ProviderError(f"provider {self.expected_provider} has invalid operations")
        if any(
            not isinstance(allowed_operation, str) or not allowed_operation or len(allowed_operation) > 128
            for allowed_operation in operation_rows
        ):
            raise ProviderError(f"provider {self.expected_provider} has invalid operations")
        if operation not in set(operation_rows):
            raise ProviderError(f"operation {operation} is not allowed for provider {self.expected_provider}")
        if operation.startswith("cloud.") and self.expected_provider != "uqc-cloud":
            raise ProviderError(f"provider {self.expected_provider} may not invoke {operation}")
        if operation.startswith("hpc.") and self.expected_provider != "hpc-slurm-ssh":
            raise ProviderError(f"provider {self.expected_provider} may not invoke {operation}")
        if self.allow_twin_id != (self.expected_provider == "ionstack-twinrun"):
            raise ProviderError(f"provider {self.id} has an invalid twin_id permission")
        from company_agent.invoke import validate_invocation

        error = validate_invocation(event["tool"], payload)
        if error is not None:
            raise ProviderError(error)
        if not re.fullmatch(r"[a-z]+(?:\.[a-z-]+)+", operation):
            raise ProviderError("provider operation format is invalid")
        if contract.get("env") != self.url_env or contract.get("token_env", "") != self.token_env:
            raise ProviderError(f"provider environment contract mismatch for {self.expected_provider}")
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{1,127}", self.url_env):
            raise ProviderError("provider URL environment name is invalid")
        if self.token_env and not re.fullmatch(r"[A-Z][A-Z0-9_]{1,127}", self.token_env):
            raise ProviderError("provider token environment name is invalid")
        url = self.endpoint()
        if not url:
            raise ProviderError(f"{self.url_env} is not configured")
        request_id = "req_" + uuid.uuid4().hex
        body = {
            "protocol": PROVIDER_PROTOCOL,
            "operation": operation,
            "request_id": request_id,
            "payload": dict(payload),
        }
        try:
            encoded_body = json.dumps(body, allow_nan=False, separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ProviderError("provider payload is not valid JSON") from exc
        if len(encoded_body) > _MAX_RESPONSE_BYTES:
            raise ProviderError("provider request is too large")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        token = str(os.environ.get(self.token_env) or "").strip() if self.token_env else ""
        if self.token_env and not token:
            raise ProviderError(f"{self.token_env} is not configured")
        if "\r" in token or "\n" in token:
            raise ProviderError(f"{self.token_env} contains invalid characters")
        if len(token) > 8192:
            raise ProviderError(f"{self.token_env} is too long")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if operation in {"cloud.submit", "hpc.stage-file", "hpc.file-fetch"}:
            import base64

            workspace = os.environ.get("COMPANY_AGENT_TOOL_WORKSPACE", "")
            if not workspace or not os.path.isabs(workspace):
                raise ProviderError("provider operation requires the active DSH workspace")
            headers["X-Company-Workspace"] = base64.urlsafe_b64encode(workspace.encode()).decode()
        request = urllib.request.Request(
            url,
            data=encoded_body,
            headers=headers,
            method="POST",
        )
        verify_snapshot_current()
        event.update(request_id=request_id, execution_state="dispatched")
        if not emit(event):
            event.update(request_id="", execution_state="not_dispatched", error_category="internal")
            raise ProviderError("provider diagnostic channel is unavailable before dispatch")
        if requires_dispatch_record(operation):
            # The external submission needs a durable locator that survives the
            # invocation process. Without it the request must not be sent: an
            # unknown outcome could never be reconciled against platform facts.
            try:
                record_dispatch(event)
            except ReceiptError as exc:
                event.update(request_id="", execution_state="not_dispatched", error_category="internal")
                raise ProviderError("provider dispatch receipt is unavailable; request not sent") from exc
        try:
            with _OPENER.open(request, timeout=self.timeout) as response:
                status = getattr(response, "status", None)
                if status != 200:
                    raise ProviderError(f"provider {self.id} returned unexpected HTTP status")
                content_type = str(response.headers.get("Content-Type") or "").casefold()
                media_type = content_type.split(";", 1)[0].strip()
                if media_type != "application/json" and not (
                    media_type.startswith("application/") and media_type.endswith("+json")
                ):
                    raise ProviderError(f"provider {self.id} returned a non-JSON content type")
                content_length = response.headers.get("Content-Length")
                if content_length is not None:
                    try:
                        declared_size = int(content_length)
                    except ValueError as exc:
                        raise ProviderError(f"provider {self.id} returned an invalid Content-Length") from exc
                    if declared_size < 0 or declared_size > _MAX_RESPONSE_BYTES:
                        raise ProviderError(f"provider {self.id} response is too large")
                raw_bytes = response.read(_MAX_RESPONSE_BYTES + 1)
                if len(raw_bytes) > _MAX_RESPONSE_BYTES:
                    raise ProviderError(f"provider {self.id} response is too large")
                raw = raw_bytes.decode("utf-8")
        except urllib.error.HTTPError as exc:
            # Remote error text is untrusted data, even without credential keywords.
            exc.close()
            if exc.code in {401, 403}:
                event["error_category"] = "authentication"
                raise _decisive(f"provider {self.id} rejected authentication") from exc
            if 400 <= exc.code < 500:
                event["error_category"] = "remote"
                raise _decisive(
                    f"provider {self.id} returned HTTP {exc.code}"
                ) from exc
            # 5xx answers may have executed the submission already: not decisive.
            event["error_category"] = "remote"
            raise ProviderError(f"provider {self.id} returned HTTP {exc.code}") from exc
        except ProviderError:
            raise
        except (UnicodeError, urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
            event["error_category"] = "timeout" if (
                isinstance(exc, TimeoutError) or isinstance(getattr(exc, "reason", None), TimeoutError)
            ) else "transport"
            raise ProviderError(f"provider {self.id} is unreachable") from exc
        try:
            envelope = strict_json_loads(raw) if raw else {}
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            message = str(exc)
            if "duplicate JSON field" in message:
                raise ProviderError(f"provider {self.id} returned a duplicate JSON field") from exc
            if "non-finite JSON number" in message:
                raise ProviderError(message) from exc
            raise ProviderError(f"provider {self.id} returned invalid JSON") from exc
        if not isinstance(envelope, dict) or envelope.get("protocol") != PROVIDER_PROTOCOL:
            raise ProviderError(f"provider {self.id} returned an invalid protocol envelope")
        if set(envelope).intersection({"token", "secret", "api_key", "password", "authorization"}):
            raise ProviderError(f"provider {self.id} returned credential-shaped envelope fields")
        if not isinstance(envelope.get("ok"), bool):
            raise ProviderError(f"provider {self.id} returned an invalid ok flag")
        if not isinstance(envelope.get("provider"), str):
            raise ProviderError(f"provider {self.id} returned an invalid provider identity")
        if len(envelope["provider"]) > 128:
            raise ProviderError(f"provider {self.id} returned an oversized provider identity")
        if not isinstance(envelope.get("request_id"), str):
            raise ProviderError(f"provider {self.id} returned an invalid request_id")
        if len(envelope["request_id"]) > 128:
            raise ProviderError(f"provider {self.id} returned an oversized request_id")
        if envelope.get("provider") != self.expected_provider:
            raise ProviderError(f"provider identity mismatch for {self.id}")
        if envelope.get("request_id") != request_id:
            raise ProviderError(f"provider request_id mismatch for {self.id}")
        if not re.fullmatch(r"req_[0-9a-f]{32}", envelope["request_id"]):
            raise ProviderError(f"provider {self.id} returned an invalid request_id format")
        if isinstance(envelope, dict) and "result" in envelope and envelope.get("ok") is not True:
            raise ProviderError(f"provider {self.id} returned result data in an error envelope")
        if envelope.get("ok") is not True:
            allowed_error_keys = {"protocol", "ok", "provider", "request_id", "error"}
            unknown_error_keys = set(envelope) - allowed_error_keys
            if unknown_error_keys:
                raise ProviderError(f"provider {self.id} returned unknown error envelope fields")
            if not isinstance(envelope.get("error"), str):
                raise ProviderError(f"provider {self.id} returned an invalid error field")
            # The provider answered authoritatively with a refusal: decisive,
            # never an "outcome unknown" situation for reconciliation.
            event["error_category"] = "remote"
            raise _decisive(f"provider {self.id} failed")
        if envelope.get("ok") is True and "error" in envelope:
            raise ProviderError(f"provider {self.id} returned error data in a success envelope")
        allowed_envelope_keys = {"protocol", "ok", "provider", "request_id", "result"}
        unknown_envelope_keys = set(envelope) - allowed_envelope_keys
        if unknown_envelope_keys:
            raise ProviderError(f"provider {self.id} returned unknown envelope fields")
        result = envelope.get("result")
        if not isinstance(result, dict):
            raise ProviderError(f"provider {self.id} returned a non-object result")
        _validate_json_value(result)
        if self.allow_twin_id != (self.expected_provider == "ionstack-twinrun"):
            raise ProviderError(f"provider {self.id} has an invalid twin_id permission")
        if "twin_id" in result and self.expected_provider == "ionstack-twinrun" and operation != "device.run":
            raise ProviderError(f"provider {self.id} may only return twin_id from device.run")
        if "twin_id" in result and not self.allow_twin_id:
            raise ProviderError(f"provider {self.id} is not allowed to return twin_id")
        if not self.allow_twin_id and _contains_key(result, "twin_id"):
            raise ProviderError(f"provider {self.id} is not allowed to return nested twin_id")
        allow_asset_list = self.expected_provider == "uniqon" and operation == "asset.list"
        allow_twin_id = self.allow_twin_id and operation == "device.run"
        try:
            validate_output_content(result, allow_twin_id=allow_twin_id)
        except ValueError as exc:
            raise ProviderError(f"provider {self.id} returned forbidden or oversized result data") from exc
        if has_forbidden_output(result, allow_twin_id=allow_twin_id, allow_asset_list=allow_asset_list):
            raise ProviderError(f"provider {self.id} returned forbidden or oversized result data")
        return short_result(result, allow_twin_id=allow_twin_id, allow_asset_list=allow_asset_list)


def clients() -> tuple[ProviderClient, ...]:
    rows = load_providers().get("providers") or []
    result: list[ProviderClient] = []
    identities: set[str] = set()
    kinds: set[str] = set()
    try:
        for row in rows:
            if set(row) != {"id", "kind", "env", "token_env", "operations"}:
                raise ProviderError("provider contract is invalid")
            provider_id = str(row["id"])
            kind = str(row["kind"])
            if not re.fullmatch(r"[a-z][a-z0-9-]{1,127}", provider_id):
                raise ProviderError("provider contract is invalid")
            if not provider_id or provider_id in identities or kind in kinds:
                raise ProviderError("provider contract is invalid")
            identities.add(provider_id)
            kinds.add(kind)
            if kind not in {"platform", "simulator", "compiler", "device", "compute", "cloud"}:
                raise ProviderError("provider contract is invalid")
            result.append(
                ProviderClient(
                    id=kind,
                    url_env=str(row["env"]),
                    expected_provider=provider_id,
                    token_env=str(row.get("token_env") or ""),
                    allow_twin_id=provider_id == "ionstack-twinrun",
                )
            )
    except (KeyError, TypeError, ValueError) as exc:
        raise ProviderError("provider contract is invalid") from exc
    return tuple(result)


def client_by_provider(provider_id: str) -> ProviderClient:
    for client in clients():
        if client.expected_provider == provider_id:
            return client
    raise ProviderError(f"provider {provider_id} is not in the provider contract")
