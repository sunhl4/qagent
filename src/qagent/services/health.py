from __future__ import annotations

from typing import Any

from qagent.adapters.cloud import cloud_status, qchem_url, qdata_url, hub_url, twin_url
from qagent.adapters.homes import qchem_bin, qdata_bin
from qagent.adapters.route import mapqccd_estimate
from qagent.adapters.support import try_http_json, try_http_json_url

_PROBE_CIRCUIT = {"body": {"instructions": [{"name": "H", "qubits": [0]}], "n_qubits": 2}}


def _estimate_ok() -> bool:
    try:
        row = mapqccd_estimate({"circuit": _PROBE_CIRCUIT})
        return isinstance(row, dict) and "makespan_ns" in row
    except (ValueError, RuntimeError, TypeError, KeyError):
        return False


def _probe_label(url: str | None, live: bool) -> str:
    if not url:
        return "not_configured"
    return "reachable" if live else "unreachable"


def science_health() -> dict[str, Any]:
    """Probe configured ports only. Never mints handles or cards. Empty URL is not localhost."""
    twin_base = twin_url()
    twin = try_http_json("GET", "/v1/twin/identity") if twin_base else None
    qdata_base = qdata_url()
    qdata = try_http_json_url(f"{qdata_base}/v1/healthz") if qdata_base else None
    qchem_base = qchem_url()
    qchem_http = try_http_json_url(f"{qchem_base}/v1/healthz") if qchem_base else None
    qchem_http_ok = bool(isinstance(qchem_http, dict) and qchem_http.get("status") == "ok") or (
        bool(qchem_base) and try_http_json_url(qchem_base) is not None
    )
    hub_base = hub_url()
    hub = try_http_json_url(f"{hub_base}/v1/index") if hub_base else None
    if hub_base and hub is None:
        hub = try_http_json_url(hub_base)
    qdata_ok = bool(isinstance(qdata, dict) and qdata.get("status") == "ok")
    return {
        "twin_live": bool(twin),
        "qdata_live": qdata_ok,
        "qchem_live": bool(qchem_bin()) or qchem_http_ok,
        "qdata_cli": bool(qdata_bin()),
        "estimate_ok": _estimate_ok(),
        "runtime_url": "http://127.0.0.1:3081",
        "qdata_cloud": _probe_label(qdata_base, qdata_ok),
        "qchem_cloud": _probe_label(qchem_base, qchem_http_ok),
        "twin_cloud": _probe_label(twin_base, bool(twin)),
        "hub_cloud": _probe_label(hub_base, bool(isinstance(hub, dict))),
        "cloud": cloud_status(),
    }


def health_lamps() -> dict[str, bool | int]:
    """Four face lamps. Twin live is not estimate health."""
    health = science_health()
    from qagent.services.notify import asks_face

    pending = asks_face().get("pending")
    return {
        "twin": bool(health["twin_live"]),
        "estimate": bool(health.get("estimate_ok")),
        "qdata": bool(health["qdata_live"]),
        "asks": int(pending or 0),
    }
