#!/usr/bin/env python3
"""UQC cloud platform probe over the official Socket.IO SDK (uqc_client).

The cloud login is token-based: UQC(token=...) connects to SERVER_HOST:SERVER_PORT
over Socket.IO and authenticates with the sk- prefixed API key. The REST gateway
(/api/v1/*) is a separate auth layer and does not accept this key, so the workspace
status probe must use the SDK transport.

Reads configuration from the environment (never argv so the key stays out of
process listings):
  UQC_CLOUD_API_KEY  sk- prefixed API key (required)
  UQC_CLOUD_HOST     required; no baked host
  UQC_CLOUD_PORT     required; no baked port

Prints exactly one JSON line:
  {"connected": true,  "chips": [{...normalized device rows...}]}
  {"connected": false, "reason": "unreachable" | "auth_failed" | "probe_error", "detail": "..."}

Never prints the key itself.
"""
from __future__ import annotations

import json
import os
import signal
import socket
import sys

TIMEOUT_S = 40


class _Timeout(Exception):
    pass


def _alarm(_sig, _frame):
    raise _Timeout()


def _arm() -> None:
    alarm = getattr(signal, "SIGALRM", None)
    if alarm is None:
        return
    signal.signal(alarm, _alarm)
    signal.alarm(TIMEOUT_S)


def _disarm() -> None:
    if getattr(signal, "SIGALRM", None) is None:
        return
    signal.alarm(0)


def _resolve(host: str) -> str:
    try:
        return socket.gethostbyname(host)
    except OSError:
        return host


def _normalize_chips(chips) -> list:
    rows = []
    if not isinstance(chips, dict):
        return rows
    for name, chip in chips.items():
        if not isinstance(chip, dict):
            rows.append({"id": str(name), "name": str(name), "status": "未知"})
            continue
        info = chip.get("device_info") if isinstance(chip.get("device_info"), dict) else {}
        status = str(chip.get("status") or info.get("chip_status") or "未知")
        kind = str(chip.get("chip_type") or "")
        rows.append({
            "id": str(name),
            "name": str(chip.get("description") or chip.get("name") or name),
            "status": status,
            "state": status,
            "qubits": chip.get("qubits") if chip.get("qubits") is not None else info.get("qubit_count"),
            "region": chip.get("region") or "",
            "chip_type": kind,
            "kind": kind,
            "max_shots": info.get("max_shots") or "",
        })
    return rows


def main() -> int:
    token = (os.environ.get("UQC_CLOUD_API_KEY") or "").strip()
    host = (os.environ.get("UQC_CLOUD_HOST") or "").strip()
    port_text = (os.environ.get("UQC_CLOUD_PORT") or "").strip()
    if not token:
        print(json.dumps({"connected": False, "reason": "missing_api_key",
                          "detail": "UQC_CLOUD_API_KEY 未配置"}, ensure_ascii=False))
        return 0
    if not host or not port_text.isdigit():
        print(json.dumps({"connected": False, "reason": "missing_endpoint",
                          "detail": "UQC_CLOUD_HOST 或 UQC_CLOUD_PORT 未配置"}, ensure_ascii=False))
        return 0
    port = int(port_text)

    _arm()
    try:
        # The SDK reads SERVER_HOST/SERVER_PORT via pydantic-settings at init;
        # translate our names so the UI-configured target wins.
        if os.environ.get("UQC_CLOUD_HOST"):
            os.environ["SERVER_HOST"] = os.environ["UQC_CLOUD_HOST"]
        if os.environ.get("UQC_CLOUD_PORT"):
            os.environ["SERVER_PORT"] = os.environ["UQC_CLOUD_PORT"]
        from uqc_client import UQC
        client = UQC(token=token)
        chips = client.get_chips()
        client.disconnect() if hasattr(client, "disconnect") else None
    except _Timeout:
        print(json.dumps({"connected": False, "reason": "unreachable",
                          "detail": f"Socket.IO 连接 {host}:{port} 超时（{TIMEOUT_S}s）"}, ensure_ascii=False))
        return 0
    except ImportError as exc:
        print(json.dumps({"connected": False, "reason": "probe_error",
                          "detail": f"uqc_client 未安装: {exc}"}, ensure_ascii=False))
        return 0
    except socket.gaierror as exc:
        print(json.dumps({"connected": False, "reason": "unreachable",
                          "detail": f"DNS 解析失败 {host}: {exc}"}, ensure_ascii=False))
        return 0
    except ConnectionRefusedError as exc:
        print(json.dumps({"connected": False, "reason": "unreachable",
                          "detail": f"连接被拒绝 {_resolve(host)}:{port}: {exc}"}, ensure_ascii=False))
        return 0
    except OSError as exc:
        detail = f"网络不可达 {host}:{port}: {exc}"
        try:  # SDK wraps auth/network errors too; keep the classifier honest
            import uqc_client.uqc as uq
            if "token" in str(exc).lower() or "auth" in str(exc).lower():
                detail = str(exc)[:160]
        except Exception:
            pass
        print(json.dumps({"connected": False, "reason": "unreachable",
                          "detail": detail[:160]}, ensure_ascii=False))
        return 0
    except Exception as exc:  # SDK auth failure emerges as UQC*Error here
        text = str(exc)[:160]
        lowered = text.lower()
        if any(word in lowered for word in ("token", "auth", "401", "403", "forbidden", "unauthorized")):
            print(json.dumps({"connected": False, "reason": "auth_failed", "detail": text}, ensure_ascii=False))
        else:
            print(json.dumps({"connected": False, "reason": "probe_error", "detail": text}, ensure_ascii=False))
        return 0
    finally:
        _disarm()

    print(json.dumps({"connected": True, "chips": _normalize_chips(chips)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
