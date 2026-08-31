from __future__ import annotations

from qagent.adapters.homes import qchem_bin, qdata_bin, qdata_probe_url
from qagent.adapters.route import mapqccd_estimate
from qagent.adapters.support import try_http_json, try_http_json_url

_PROBE_CIRCUIT = {"body": {"instructions": [{"name": "H", "qubits": [0]}], "n_qubits": 2}}


def _estimate_ok() -> bool:
    try:
        row = mapqccd_estimate({"circuit": _PROBE_CIRCUIT})
        return isinstance(row, dict) and "makespan_ns" in row
    except (ValueError, RuntimeError, TypeError, KeyError):
        return False


def science_health() -> dict[str, bool | str]:
    """Probe live ports. Never mints handles or cards."""
    twin = try_http_json("GET", "/v1/twin/identity")
    qdata = try_http_json_url(f"{qdata_probe_url()}/v1/healthz")
    return {
        "twin_live": bool(twin),
        "qdata_live": bool(isinstance(qdata, dict) and qdata.get("status") == "ok"),
        "qchem_live": bool(qchem_bin()),
        "qdata_cli": bool(qdata_bin()),
        "estimate_ok": _estimate_ok(),
        "runtime_url": "http://127.0.0.1:3081",
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
