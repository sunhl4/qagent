from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from types import MappingProxyType
from typing import Any

from company_agent.jsonutil import loads as strict_json_loads
from company_agent.schema import SchemaError, validate_schema_definition

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
_CONTRACT_NAMES = (
    "tools", "results", "providers", "capabilities", "policy", "presets", "templates", "skills",
    "tenants", "budgets", "superagent",
)


@dataclass(frozen=True)
class ContractSnapshot:
    root: Path
    documents: Any  # Read-only mapping of names to immutable canonical JSON bytes.
    digest: str


_SNAPSHOT: ContextVar[ContractSnapshot | None] = ContextVar("contract_snapshot", default=None)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


@contextmanager
def contract_snapshot() -> Iterator[ContractSnapshot]:
    """Pin one content-addressed contract set for one invocation, never across calls."""
    existing = _SNAPSHOT.get()
    if existing is not None:
        yield existing
        return
    root = contract_root()
    documents = {f"{name}.json": _canonical(read_json(root / f"{name}.json")) for name in _CONTRACT_NAMES}
    digest = hashlib.sha256()
    for name, content in documents.items():
        digest.update(name.encode("ascii") + b"\0" + content + b"\0")
    snapshot = ContractSnapshot(root, MappingProxyType(documents), "sha256:" + digest.hexdigest())
    token = _SNAPSHOT.set(snapshot)
    try:
        # Validate every contract before any invocation can have side effects.
        _validate_contract_graph()
        yield snapshot
    finally:
        _SNAPSHOT.reset(token)


def _validate_contract_graph() -> None:
    from company_agent.capabilities import list_capabilities
    from company_agent.policy import _policy_contract

    tools = load_tools()
    load_result_policy()
    providers = {row["id"]: row for row in load_providers()["providers"]}
    capabilities = {row.id: row for row in list_capabilities()}
    policy = _policy_contract()
    if (policy["device_provider"] != "ionstack-twinrun" or policy["device_provenance"] != "qccd-twin"
        or policy["device_ask_presets"] != ["lab", "sign"]
        or policy["device_deny_presets"] != ["boot", "algo"]):
        raise RuntimeError("invalid device policy contract")
    if (policy.get("cloud_submit_tool") != "quantum_cloud_submit"
        or policy.get("cloud_submit_provider") != "uqc-cloud"
        or policy.get("cloud_submit_ask_presets") != ["lab", "sign"]
        or policy.get("cloud_submit_deny_presets") != ["boot", "algo"]
        or policy.get("cloud_submission") != {
            "target_scope": "simulators_only", "artifact_scope": "workspace_openqasm_file",
            "automatic_retries": 0,
        }):
        raise RuntimeError("invalid cloud submission policy contract")
    expected_providers = {"company.algorithm": "uniqon",
                          "company.asset": "uniqon",
                          "quantum.simulation": "independent-simulator",
                          "quantum.compilation": "independent-compiler",
                          "quantum.device": "ionstack-twinrun",
                          "compute.cloud": "uqc-cloud",
                          "compute.hpc": "hpc-slurm-ssh",
                          "company.knowledge": "company-knowledge", "company.workflow": "company-agent",
                          "company.latex": "company-latex", "company.plan": "company-plan",
                          "company.office": "company-office",
                          "company.portal": "company-portal"}
    referenced = set()
    operations_by_provider: dict[str, set[str]] = {name: set() for name in providers}
    for capability in capabilities.values():
        if (capability.provider != expected_providers[capability.id]
            or capability.contract_version != capability.id + "/2.0"):
            raise RuntimeError("invalid capability provider or version contract")
        for name in capability.tools:
            row = tools.get(name)
            if row is None or row["capability"] != capability.id or name in referenced:
                raise RuntimeError("invalid tool capability mapping")
            if not (set(row["input_handles"]) | set(row["output_handles"])) <= set(capability.handles):
                raise RuntimeError("invalid tool handle mapping")
            referenced.add(name)
            if capability.provider in providers:
                if row["operation"] not in providers[capability.provider]["operations"]:
                    raise RuntimeError("invalid provider operation mapping")
                operations_by_provider[capability.provider].add(row["operation"])
    if any(set(row["operations"]) != operations_by_provider[name] for name, row in providers.items()):
        raise RuntimeError("incomplete provider operation contract")
    if referenced != set(tools):
        raise RuntimeError("incomplete capability contract")
    for preset, row in load_presets()["presets"].items():
        visible = row["visible_tools"]
        if (not isinstance(visible, list) or any(not isinstance(name, str) for name in visible)
            or len(visible) != len(set(visible)) or not set(visible) <= set(tools)
            or ("quantum_device_run" in visible) != (preset in {"lab", "sign"})
            or ("quantum_cloud_submit" in visible) != (preset in {"lab", "sign"})
            or ("hpc_submit" in visible) != (preset in {"lab", "sign"})
            or ("hpc_stage_file" in visible) != (preset in {"lab", "sign"})
            or ("hpc_job_cancel" in visible) != (preset in {"lab", "sign"})
            or ("hpc_dir_create" in visible) != (preset in {"lab", "sign"})
            or ("hpc_file_remove" in visible) != (preset in {"lab", "sign"})):
            raise RuntimeError("invalid preset visibility contract")
    builtins = load_managed_builtins()
    if any(name in tools for name in builtins):
        raise RuntimeError("invalid managed builtin contract: name collision")
    capability_tools = {name for capability in capabilities.values() for name in capability.tools}
    if builtins.keys() & capability_tools:
        raise RuntimeError("invalid managed builtin contract: capability mapping")
    templates = load_templates()
    for template in templates.values():
        if any(source not in tools for source in template["sources"]):
            raise RuntimeError("invalid analysis template source contract")
    for row in load_skills().values():
        if (
            (WORKSPACE_ROOT / row["path"]).is_file()
            and not (WORKSPACE_ROOT / "skills" / row["name"]).is_dir()
        ):
            # Admitted content digests are checked at mount/sync time; the
            # workspace gate keeps the registry listing consistent on disk.
            raise RuntimeError("invalid skill registry contract: missing skill directory")


def verify_snapshot_current() -> None:
    """Recheck content immediately before network dispatch; changed contracts fail closed."""
    snapshot = _SNAPSHOT.get()
    if snapshot is None:
        raise RuntimeError("provider dispatch requires a contract snapshot")
    if contract_root() != snapshot.root or any(
        _canonical(read_json(snapshot.root / name)) != content
        for name, content in snapshot.documents.items()
    ):
        raise RuntimeError("Company Agent contracts changed before dispatch")


def current_contract_digest() -> str:
    with contract_snapshot() as snapshot:
        return snapshot.digest



def _workspace_contract_root() -> Path | None:
    package_dir = Path(__file__).resolve().parent
    candidate = WORKSPACE_ROOT / "contracts"
    if package_dir.parent.name == "src" and (WORKSPACE_ROOT / "pyproject.toml").is_file():
        return candidate
    return None


def _installed_contract_root() -> Path | None:
    try:
        distribution = metadata.distribution("unitqc-company-agent")
    except metadata.PackageNotFoundError:
        return None
    for file in distribution.files or ():
        text = str(file).replace("\\", "/")
        if text.endswith("share/unitqc-company-agent/contracts/tools.json"):
            return Path(distribution.locate_file(file)).parent
    return None


def _installed_prefix_contract_root() -> Path | None:
    package_dir = Path(__file__).resolve().parent
    for parent in (package_dir.parent, *package_dir.parents):
        candidate = parent / "share" / "unitqc-company-agent" / "contracts"
        if (candidate / "tools.json").is_file():
            return candidate
    return None


def contract_root() -> Path:
    configured = str(os.environ.get("COMPANY_AGENT_CONTRACTS_DIR") or "").strip()
    if "\x00" in configured:
        raise RuntimeError("invalid COMPANY_AGENT_CONTRACTS_DIR")
    try:
        value = Path(configured).expanduser() if configured else None
    except RuntimeError as exc:
        raise RuntimeError("invalid COMPANY_AGENT_CONTRACTS_DIR") from exc
    if value is not None and not value.is_absolute():
        raise RuntimeError("COMPANY_AGENT_CONTRACTS_DIR must be an absolute path")
    if configured:
        configured_path = value
        unavailable = (
            configured_path is None
            or configured_path.is_symlink()
            or not (configured_path / "tools.json").is_file()
        )
        if unavailable:
            raise RuntimeError("configured Company Agent contracts are unavailable")
        return configured_path
    for locate in (_workspace_contract_root, _installed_contract_root, _installed_prefix_contract_root):
        candidate = locate()
        if candidate is not None and (candidate / "tools.json").is_file():
            return candidate
    raise RuntimeError("Company Agent contracts are not installed")


def read_json(path: Path) -> Any:
    if not isinstance(path, Path):
        raise TypeError("contract path must be a pathlib.Path")
    try:
        # O_NOFOLLOW closes the final-component symlink race; fingerprint the open file.
        nofollow_flag = getattr(os, "O_NOFOLLOW", 0)
        nonblock_flag = getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(path, os.O_RDONLY | nofollow_flag | nonblock_flag)
        with os.fdopen(descriptor, "rb") as stream:
            initial = os.fstat(stream.fileno())
            if not stat.S_ISREG(initial.st_mode) or initial.st_size > 1_000_000:
                raise RuntimeError("contract is not a bounded regular file")
            source = stream.read(1_000_001)
            final = os.fstat(stream.fileno())
        def fingerprint(value):
            return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)

        if len(source) > 1_000_000 or fingerprint(initial) != fingerprint(final):
            raise RuntimeError("contract changed while reading")
        if path.is_symlink() or fingerprint(path.stat()) != fingerprint(final):
            raise RuntimeError("contract changed while reading")
        payload = strict_json_loads(source.decode("utf-8"))
    except (OSError, UnicodeError, ValueError, TypeError, RuntimeError) as exc:
        raise RuntimeError(f"invalid Company Agent contract: {path.name}") from exc
    return payload


def _load_object(name: str) -> dict[str, Any]:
    if not isinstance(name, str) or not re.fullmatch(r"[a-z]+\.json", name):
        raise RuntimeError("invalid Company Agent contract name")
    snapshot = _SNAPSHOT.get()
    payload = (
        strict_json_loads(snapshot.documents[name].decode("utf-8"))
        if snapshot is not None and name in snapshot.documents
        else read_json(contract_root() / name)
    )
    if not isinstance(payload, dict):
        raise RuntimeError(f"invalid Company Agent contract: {name}")
    return payload


def load_tools() -> dict[str, dict[str, Any]]:
    raw = _load_object("tools.json")
    if set(raw) != {"version", "handles", "tools", "managed_builtins"}:
        raise RuntimeError("invalid Company Agent contract: tools.json")
    if raw.get("version") != "2.0.0" or raw.get("handles") != ["asset_id", "circuit_id", "twin_id"]:
        raise RuntimeError("invalid Company Agent contract: tools.json")
    rows = raw.get("tools")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise RuntimeError("invalid Company Agent contract: tools.json")
    for row in rows:
        if set(row) != {
            "name",
            "capability",
            "operation",
            "input_handles",
            "output_handles",
            "description",
            "parameters",
            "output",
        }:
            raise RuntimeError("invalid Company Agent contract: tools.json")
    names = [str(row.get("name") or "") for row in rows]
    if any(not re.fullmatch(r"(?:company|quantum|hpc)_[a-z0-9_]{1,127}", name) for name in names):
        raise RuntimeError("invalid Company Agent contract: tools.json")
    for row in rows:
        if not isinstance(row.get("description"), str) or not row["description"].strip():
            raise RuntimeError("invalid Company Agent contract: tools.json")
        for key in ("capability", "operation"):
            if not isinstance(row.get(key), str) or not row[key] or len(row[key]) > 128:
                raise RuntimeError("invalid Company Agent contract: tools.json")
        for key in ("input_handles", "output_handles"):
            handles = row.get(key)
            if not isinstance(handles, list) or any(handle not in raw["handles"] for handle in handles):
                raise RuntimeError("invalid Company Agent contract: tools.json")
            if len(handles) != len(set(handles)):
                raise RuntimeError("invalid Company Agent contract: tools.json")
        if set(row["input_handles"]) & set(row["output_handles"]):
            raise RuntimeError("invalid Company Agent contract: tools.json")
        for key in ("parameters", "output"):
            schema = row.get(key)
            if not isinstance(schema, dict) or schema.get("type") != "object":
                raise RuntimeError("invalid Company Agent contract: tools.json")
            if schema.get("additionalProperties") is not False:
                raise RuntimeError("invalid Company Agent contract: tools.json")
            try:
                validate_schema_definition(schema)
            except SchemaError as exc:
                raise RuntimeError("invalid Company Agent contract: tools.json") from exc
    expected_names = {
        "company_work_item",
        "company_capabilities",
        "company_knowledge_search",
        "company_fetch", "company_table_profile",
        "company_workspace_reference", "company_analysis_render",
        "company_office_analyze",
        "company_office_create",
        "company_office_compare",
        "company_office_edit",
        "company_office_validate",
        "company_office_chart",
        "company_office_matter",
        "company_office_audit",
        "company_office_pptx",
        "company_office_convert",
        "company_office_open",
        "company_office_compute",
        "company_office_deliver",
        "company_office_review_table",
        "company_office_files",
        "company_office_fix",
        "company_office_surface",
        "company_workflow_validate",
        "quantum_algorithm_catalog",
        "quantum_algorithm_run",
        "quantum_asset_list",
        "quantum_asset_get",
        "quantum_asset_metrics",
        "quantum_circuit_export",
        "quantum_simulate",
        "quantum_compile_estimate",
        "quantum_device_identity",
        "quantum_device_run",
        "quantum_cloud_devices",
        "quantum_cloud_submit",
        "quantum_cloud_status",
        "quantum_cloud_result",
        "hpc_queue",
        "hpc_job_status",
        "hpc_script_check",
        "hpc_resources",
        "hpc_file_list",
        "hpc_file_fetch",
        "hpc_stage_file",
        "hpc_job_cancel",
        "hpc_dir_create",
        "hpc_file_remove",
        "hpc_submit",
        "company_latex_structure",
        "company_latex_read",
        "company_latex_edit",
        "company_latex_batch_edit",
        "company_latex_check",
        "company_latex_compile",
        "company_latex_diff",
        "company_latex_checkpoint",
        "company_latex_revert",
        "company_latex_pull",
        "company_latex_push",
        "company_latex_overleaf_pull",
        "company_latex_overleaf_push",
        "company_latex_overleaf_status",
        "company_plan_projects",
        "company_plan_issues",
        "company_plan_issue_get",
        "company_plan_issue_create",
        "company_plan_mrs",
        "company_plan_note_create",
        "company_plan_issue_write",
        "company_plan_milestones",
        "company_plan_milestone_create",
        "company_latex_issue_note",
        "company_portal_open",
    }
    if set(names) != expected_names:
        raise RuntimeError("invalid Company Agent contract: tools.json")
    if not all(names) or len(names) != len(set(names)):
        raise RuntimeError("invalid Company Agent contract: tools.json")
    return {name: dict(row) for name, row in zip(names, rows, strict=True)}


def load_tools_for_preset(preset: str) -> dict[str, dict[str, Any]]:
    if not isinstance(preset, str) or not preset or len(preset) > 32:
        raise KeyError("invalid preset")
    tools = load_tools()
    presets = load_presets().get("presets") or {}
    row = presets.get(preset)
    if not isinstance(row, dict):
        raise KeyError(f"unknown preset {preset!r}")
    names = row.get("visible_tools") or []
    if not isinstance(names, list) or any(not isinstance(name, str) for name in names):
        raise KeyError(f"preset {preset!r} has an invalid tool list")
    if len(names) != len(set(names)) or any(name not in tools for name in names):
        raise KeyError(f"preset {preset!r} has an invalid tool list")
    return {name: tools[name] for name in names}


def load_budgets() -> dict[str, Any]:
    """Read the termination-budget contract; any deviation disables the budget check."""
    raw = _load_object("budgets.json")
    if set(raw) != {"version", "fail_closed", "turn_env", "ledger", "limits"}:
        raise RuntimeError("invalid Company Agent contract: budgets.json")
    if raw["version"] != "1.0.0" or raw["fail_closed"] is not True:
        raise RuntimeError("invalid Company Agent contract: budgets.json")
    turn_env = raw["turn_env"]
    if (
        not isinstance(turn_env, str)
        or not re.fullmatch(r"COMPANY_AGENT_[A-Z0-9_]{3,64}", turn_env)
    ):
        raise RuntimeError("invalid Company Agent contract: budgets.json")
    ledger = raw["ledger"]
    if (
        not isinstance(ledger, dict)
        or set(ledger) != {"dir_name", "max_file_bytes", "max_turn_key_bytes"}
        or ledger["dir_name"] != "budgets"
        or not isinstance(ledger["max_file_bytes"], int)
        or isinstance(ledger["max_file_bytes"], bool)
        or not 64 <= ledger["max_file_bytes"] <= 1_048_576
        or not isinstance(ledger["max_turn_key_bytes"], int)
        or isinstance(ledger["max_turn_key_bytes"], bool)
        or not 64 <= ledger["max_turn_key_bytes"] <= 4096
    ):
        raise RuntimeError("invalid Company Agent contract: budgets.json")
    limits = raw["limits"]
    if not isinstance(limits, dict) or set(limits) != {
        "invocations", "wall_ms", "approval_waits", "device_runs", "submissions",
    }:
        raise RuntimeError("invalid Company Agent contract: budgets.json")
    for key, bound in (
        ("invocations", 4096), ("wall_ms", 86_400_000),
        ("approval_waits", 512), ("device_runs", 64), ("submissions", 64),
    ):
        value = limits[key]
        if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= bound:
            raise RuntimeError("invalid Company Agent contract: budgets.json")
    return raw


def load_managed_builtins() -> dict[str, set[str]]:
    """Read the managed DSH-native tool allowlist out of the contract.

    Returns a mapping from builtin tool name to the set of presets it is
    approved for. Unknown fields, malformed names, duplicates, phrases outside
    the preset vocabulary, or collisions with company/quantum tool names all
    fail closed: a broken managed_builtins contract disables the catalog.
    """
    raw = _load_object("tools.json").get("managed_builtins")
    if not isinstance(raw, dict) or set(raw) != {
        "description", "tools", "excluded_from_managed_list",
    }:
        raise RuntimeError("invalid Company Agent contract: tools.json managed_builtins")
    if not isinstance(raw["description"], str) or "company-agent invoke" not in raw["description"]:
        raise RuntimeError("invalid Company Agent contract: tools.json managed_builtins")
    rows = raw["tools"]
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("invalid Company Agent contract: tools.json managed_builtins")
    result: dict[str, set[str]] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "name", "source", "package", "description", "presets",
        }:
            raise RuntimeError("invalid Company Agent contract: tools.json managed_builtins")
        name = row["name"]
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"[a-z_][a-z0-9_]{0,63}", name)
            or name in result
        ):
            raise RuntimeError("invalid Company Agent contract: tools.json managed_builtins")
        if row["source"] != "dsh-native":
            raise RuntimeError("invalid Company Agent contract: tools.json managed_builtins")
        package = row["package"]
        if not isinstance(package, str) or not re.fullmatch(r"@deepseek-ai/dsh-tool-[a-z-]+", package):
            raise RuntimeError("invalid Company Agent contract: tools.json managed_builtins")
        description = row["description"]
        if (
            not isinstance(description, str)
            or not description.strip()
            or len(description.encode("utf-8")) > 2000
        ):
            raise RuntimeError("invalid Company Agent contract: tools.json managed_builtins")
        presets = row["presets"]
        approved = {"boot", "lab", "algo", "sign"}
        if (
            not isinstance(presets, list)
            or not presets
            or len(presets) != len(set(presets))
            or any(preset not in approved for preset in presets)
        ):
            raise RuntimeError("invalid Company Agent contract: tools.json managed_builtins")
        result[name] = {preset for preset in presets}
    excluded = raw["excluded_from_managed_list"]
    if not isinstance(excluded, list):
        raise RuntimeError("invalid Company Agent contract: tools.json managed_builtins")
    for row in excluded:
        if (
            not isinstance(row, dict)
            or set(row) != {"name", "reason"}
            or any(not isinstance(row[key], str) or not row[key].strip() for key in row)
        ):
            raise RuntimeError("invalid Company Agent contract: tools.json managed_builtins")
    company_names = set(load_tools())
    if result.keys() & company_names:
        raise RuntimeError("invalid Company Agent contract: tools.json managed_builtins name collision")
    return result


def builtin_tools_for_preset(preset: str) -> tuple[str, ...]:
    """Managed builtin tool names approved for one preset, in contract order."""
    if not isinstance(preset, str) or not preset or len(preset) > 32:
        raise KeyError("invalid preset")
    load_managed_builtins()
    if preset not in {"boot", "lab", "algo", "sign"}:
        raise KeyError(f"unknown preset {preset!r}")
    rows = _load_object("tools.json")["managed_builtins"]["tools"]
    return tuple(row["name"] for row in rows if preset in row["presets"])


def load_capabilities() -> dict[str, Any]:
    payload = _load_object("capabilities.json")
    if set(payload) != {"version", "capabilities"} or payload.get("version") != "1.0.0":
        raise RuntimeError("invalid Company Agent contract: capabilities.json")
    rows = payload.get("capabilities")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise RuntimeError("invalid Company Agent contract: capabilities.json")
    for row in rows:
        if set(row) != {
            "id",
            "kind",
            "provider",
            "contract_version",
            "tools",
            "handles",
            "approval",
            "provenance",
        }:
            raise RuntimeError("invalid Company Agent contract: capabilities.json")
    return payload


def load_policy() -> dict[str, Any]:
    payload = _load_object("policy.json")
    expected = {
        "version",
        "fail_closed",
        "forbidden_tools",
        "device_tool",
        "device_provider",
        "device_provenance",
        "device_ask_presets",
        "device_deny_presets",
        "cloud_submit_tool",
        "cloud_submit_provider",
        "cloud_submit_ask_presets",
        "cloud_submit_deny_presets",
        "cloud_submission",
        "hpc_submit_tool",
        "hpc_submit_provider",
        "hpc_submit_ask_presets",
        "hpc_submit_deny_presets",
        "hpc_file_write_tool",
        "hpc_file_write_provider",
        "hpc_file_write_ask_presets",
        "hpc_file_write_deny_presets",
        "hpc_job_cancel_tool",
        "hpc_job_cancel_provider",
        "hpc_job_cancel_ask_presets",
        "hpc_job_cancel_deny_presets",
        "latex_write_tools",
        "latex_write_provider",
        "latex_write_ask_presets",
        "latex_write_deny_presets",
        "plan_write_tools",
        "plan_write_provider",
        "plan_write_ask_presets",
        "plan_write_deny_presets",
    }
    if set(payload) != expected or payload.get("version") != "1.0.0":
        raise RuntimeError("invalid Company Agent contract: policy.json")
    return payload


def load_presets() -> dict[str, Any]:
    payload = _load_object("presets.json")
    presets = payload.get("presets")
    if (
        set(payload) != {"version", "presets"}
        or payload.get("version") != "1.0.0"
        or not isinstance(presets, dict)
        or set(presets) != {"boot", "lab", "algo", "sign"}
    ):
        raise RuntimeError("invalid Company Agent contract: presets.json")
    for row in presets.values():
        if not isinstance(row, dict) or set(row) != {"visible_tools"}:
            raise RuntimeError("invalid Company Agent contract: presets.json")
    return payload


def load_providers() -> dict[str, Any]:
    payload = _load_object("providers.json")
    if set(payload) != {"protocol", "providers"} or payload.get("protocol") != "company-agent-provider/1.0":
        raise RuntimeError("invalid Company Agent contract: providers.json")
    rows = payload.get("providers")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise RuntimeError("invalid Company Agent contract: providers.json")
    for row in rows:
        if set(row) != {"id", "kind", "env", "token_env", "operations"}:
            raise RuntimeError("invalid Company Agent contract: providers.json")
    identities = [str(row.get("id") or "") for row in rows]
    if set(identities) != {
        "uniqon",
        "independent-simulator",
        "independent-compiler",
        "ionstack-twinrun",
        "uqc-cloud",
        "hpc-slurm-ssh",
    }:
        raise RuntimeError("invalid Company Agent contract: providers.json")
    if not all(identities) or len(identities) != len(set(identities)):
        raise RuntimeError("invalid Company Agent contract: providers.json")
    kinds = [row.get("kind") for row in rows]
    if any(not isinstance(kind, str) for kind in kinds) or set(kinds) != {
        "platform", "simulator", "compiler", "device", "compute", "cloud",
    }:
        raise RuntimeError("invalid Company Agent contract: providers.json")
    provider_kinds = {
        "uniqon": "platform", "independent-simulator": "simulator",
        "independent-compiler": "compiler", "ionstack-twinrun": "device",
        "uqc-cloud": "cloud", "hpc-slurm-ssh": "compute",
    }
    for row in rows:
        if row["kind"] != provider_kinds[row["id"]]:
            raise RuntimeError("invalid Company Agent contract: providers.json")
        for key in ("env", "token_env"):
            if not isinstance(row[key], str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{1,127}", row[key]):
                raise RuntimeError("invalid Company Agent contract: providers.json")
        operations = row["operations"]
        if (not isinstance(operations, list) or not operations
            or any(not isinstance(operation, str) or len(operation) > 128
                   or not re.fullmatch(r"[a-z]+(?:\.[a-z-]+)+", operation) for operation in operations)
            or len(operations) != len(set(operations))):
            raise RuntimeError("invalid Company Agent contract: providers.json")
    return payload


def load_result_policy() -> dict[str, Any]:
    payload = _load_object("results.json")
    if (
        set(payload)
        != {
            "version", "max_result_bytes", "provider_result", "provider_errors",
            "diagnostics", "device_execution", "output_content", "receipts",
        }
        or payload.get("version") != "2.0.0"
        or payload.get("provider_errors") != "generic_only"
    ):
        raise RuntimeError("invalid Company Agent contract: results.json")
    if payload.get("output_content") != {
        "scope": "all_tools", "known_credentials": "reject_echo",
        "reference_trust": "untrusted_reference_data", "max_safe_integer": 9007199254740991,
    }:
        raise RuntimeError("invalid Company Agent output content contract")
    diagnostics = payload.get("diagnostics")
    if diagnostics != {
        "version": "1.0", "max_event_bytes": 2000,
        "fields": ["version", "event", "tool", "operation", "request_id", "contract_digest",
                   "elapsed_ms", "status", "error_category", "execution_state"],
        "execution_states": ["not_dispatched", "dispatched", "completed", "unknown"],
        "error_categories": ["none", "validation", "transport", "authentication", "remote",
                             "invalid_result", "cancelled", "timeout", "internal"],
    }:
        raise RuntimeError("invalid Company Agent diagnostic contract")
    execution = payload.get("device_execution")
    if (
        not isinstance(execution, dict)
        or set(execution) != {"automatic_retries", "request_id_is_idempotency_key", "uncertain_failure"}
        or type(execution["automatic_retries"]) is not int
        or execution["automatic_retries"] != 0
        or execution["request_id_is_idempotency_key"] is not False
        or execution["uncertain_failure"] != "unknown"
    ):
        raise RuntimeError("invalid Company Agent execution contract")
    receipts = payload.get("receipts")
    if receipts != {
        "version": "1.2",
        "dir_env": "COMPANY_AGENT_RECEIPT_DIR",
        "fields": ["version", "record", "tool", "operation", "request_id", "contract_digest",
                   "subject", "elapsed_ms", "timestamp", "status", "error_category",
                   "execution_state", "business_ref"],
        "records": ["dispatch", "outcome"],
        "statuses": ["dispatched", "ok", "refused", "error"],
        "execution_states": ["dispatched", "completed", "unknown"],
        "binding_operations": ["cloud.submit", "device.run", "hpc.submit"],
        "ref_rules": {
            "cloud.submit": ["cloud_task"],
            "hpc.submit": ["slurm_number", "job_name"],
            "device.run": ["twin_id"],
        },
        "ref_max_bytes": 256,
        "max_record_bytes": 1600,
        "max_file_bytes": 262144,
        "max_files": 14,
        "evidence_max_age_seconds": 3600,
        "subject_max_bytes": 253,
        "trusted_subject_env": "COMPANY_AGENT_SUBJECT",
    }:
        raise RuntimeError("invalid Company Agent receipt contract")
    maximum = payload.get("max_result_bytes")
    if type(maximum) is not int or not 1 <= maximum <= 64_000:
        raise RuntimeError("invalid Company Agent contract: results.json")
    provider = payload.get("provider_result")
    limits = {"max_depth": 8, "max_mapping_items": 64, "max_list_items": 32, "max_string_bytes": 4000}
    if not isinstance(provider, dict) or set(provider) != {*limits, "forbidden_keys"}:
        raise RuntimeError("invalid Company Agent contract: results.json")
    for key, ceiling in limits.items():
        if type(provider[key]) is not int or not 1 <= provider[key] <= ceiling:
            raise RuntimeError("invalid Company Agent contract: results.json")
    forbidden = provider["forbidden_keys"]
    required = {
        "cal", "calibration", "shuttle", "bitstrings", "pauli_terms", "qasm", "qasm3",
        "circuit", "circuit_body", "counts_full", "result_full", "token", "secret",
        "api_key", "password", "authorization", "credential",
    }
    if (
        not isinstance(forbidden, list)
        or any(not isinstance(key, str) for key in forbidden)
        or len(forbidden) != len(set(forbidden))
        or not required <= set(forbidden)
    ):
        raise RuntimeError("invalid Company Agent contract: results.json")
    return payload


def load_templates() -> dict[str, dict[str, Any]]:
    """Managed analysis templates; unknown or mutated templates fail closed."""

    payload = _load_object("templates.json")
    if payload != {
        "version": "1.0.0",
        "templates": [
            {
                "id": "metric-summary",
                "kind": "metrics_table",
                "metric_schema": "scientific-metrics/1.0",
                "sources": [
                    "quantum_simulate", "quantum_compile_estimate", "quantum_asset_get",
                    "quantum_asset_metrics", "quantum_device_run", "hpc_job_status",
                ],
                "error_behavior": {"structural": "fail_closed", "domain": "flagged"},
                "outputs": {"summary": True, "charts": "bar_per_unit"},
            },
            {
                "id": "shots-audit",
                "kind": "shots_delivery",
                "metric_schema": "scientific-metrics/1.0",
                "sources": ["quantum_simulate", "quantum_device_run"],
                "error_behavior": {"structural": "fail_closed", "domain": "flagged"},
                "outputs": {"summary": True, "charts": "none"},
            },
            {
                "id": "metric-quantiles",
                "kind": "metrics_table",
                "metric_schema": "scientific-metrics/1.0",
                "sources": [
                    "quantum_simulate", "quantum_compile_estimate", "quantum_asset_get",
                    "quantum_asset_metrics", "quantum_device_run", "hpc_job_status",
                ],
                "error_behavior": {"structural": "fail_closed", "domain": "flagged"},
                "outputs": {"summary": True, "charts": "quantiles_per_unit"},
            },
            {
                "id": "shots-chart",
                "kind": "shots_delivery",
                "metric_schema": "scientific-metrics/1.0",
                "sources": ["quantum_simulate", "quantum_device_run"],
                "error_behavior": {"structural": "fail_closed", "domain": "flagged"},
                "outputs": {"summary": True, "charts": "delivery_counts"},
            },
        ],
    }:
        raise RuntimeError("invalid Company Agent analysis template contract")
    return {row["id"]: row for row in payload["templates"]}


def load_skills() -> dict[str, dict[str, Any]]:
    """Managed skill admission registry; revocation and digests are governance facts."""

    payload = _load_object("skills.json")
    if not isinstance(payload, dict) or (
        set(payload) != {"version", "skills"} or payload.get("version") != "1.0.0"
    ):
        raise RuntimeError("invalid Company Agent skill registry contract")
    rows = payload.get("skills")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise RuntimeError("invalid Company Agent skill registry contract")
    try:
        normalized = {
            "version": payload["version"],
            "skills": [
                {
                    "name": str(row["name"]),
                    "path": str(row["path"]),
                    "sha256": str(row["sha256"]),
                    "scripts": [
                        {"file": str(item["file"]), "digest": str(item["digest"])}
                        for item in row["scripts"]
                    ],
                    "revoked": row["revoked"] is True,
                    "when": [
                        {"profiles": tuple(item["profiles"]), "presets": tuple(item["presets"])}
                        for item in row["when"]
                    ],
                }
                for row in rows
            ],
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("invalid Company Agent skill registry contract") from exc
    names = [row["name"] for row in normalized["skills"]]
    if (
        any(not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", name) for name in names)
        or len(names) != len(set(names))
    ):
        raise RuntimeError("invalid Company Agent skill registry contract")
    rows = normalized["skills"]
    if any(
        not re.fullmatch(r"skills/[a-z0-9-]{1,64}/[A-Za-z0-9._-]{1,256}", row["path"])
        or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"])
        or not isinstance(row["scripts"], list)
        or any(
            not re.fullmatch(r"[0-9a-f]{64}", script["digest"])
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,255}", script["file"])
            or script["file"] != Path(script["file"]).name
            for script in row["scripts"]
        )
        or not row["when"]
        or any(
            not item["profiles"] or not item["presets"]
            or any(profile not in {"company-agent", "company-agent-minimal"} for profile in item["profiles"])
            or any(preset not in {"boot", "lab", "algo", "sign"} for preset in item["presets"])
            for item in row["when"]
        )
        or row["path"].split("/")[1] != row["name"]
        for row in rows
    ):
        raise RuntimeError("invalid Company Agent skill registry contract")
    return {row["name"]: row for row in rows}


def load_tenants() -> dict[str, Any]:
    """Tenant/service enablement contract; subjects come from the ops registry, never tool calls."""

    payload = _load_object("tenants.json")
    try:
        if not isinstance(payload, dict) or payload.get("version") != "1.0.0":
            raise RuntimeError("invalid Company Agent tenant contract")
        if set(payload) != {
            "version", "registry_env", "regimes", "states", "services",
            "line_fields", "reasons", "subject_max_bytes",
            "approved_by_max_bytes", "max_lines", "max_registry_bytes",
        }:
            raise RuntimeError("invalid Company Agent tenant contract")
        if payload["registry_env"] != "COMPANY_AGENT_TENANT_REGISTRY":
            raise RuntimeError("invalid Company Agent tenant contract")
        if payload["regimes"] != ["legacy-single-user", "registry", "unavailable"]:
            raise RuntimeError("invalid Company Agent tenant contract")
        if payload["states"] != ["approved", "pending", "revoked"]:
            raise RuntimeError("invalid Company Agent tenant contract")
        services = payload["services"]
        if (
            services != ["company.algorithm", "company.asset", "compute.cloud", "compute.hpc"]
            or len(services) != len(set(services))
        ):
            raise RuntimeError("invalid Company Agent tenant contract")
        if payload["line_fields"] != ["subject", "service", "state", "expires_epoch", "approved_by"]:
            raise RuntimeError("invalid Company Agent tenant contract")
        if payload["reasons"] != [
            "legacy", "approved", "pending", "revoked", "expired", "subject_absent",
            "registry_unavailable", "untrusted_subject",
        ]:
            raise RuntimeError("invalid Company Agent tenant contract")
        limits = {
            "subject_max_bytes": 253, "approved_by_max_bytes": 64,
            "max_lines": 1024, "max_registry_bytes": 1_048_576,
        }
        for key, ceiling in {
            "subject_max_bytes": 253,
            "approved_by_max_bytes": 64,
            "max_lines": 1024,
            "max_registry_bytes": 1_048_576,
        }.items():
            value = payload[key]
            if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= ceiling:
                raise RuntimeError("invalid Company Agent tenant contract")
        if set(limits) != set(payload) - {
            "version", "registry_env", "regimes", "states", "services", "line_fields", "reasons",
        }:
            raise RuntimeError("invalid Company Agent tenant contract")
    except RuntimeError as exc:
        raise RuntimeError("invalid Company Agent tenant contract") from exc
    return payload
