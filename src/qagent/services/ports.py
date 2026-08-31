from __future__ import annotations

from qagent.adapters.contracts import load_port_catalog
from qagent.models.invoke import PortMethod


def load_port_methods() -> list[PortMethod]:
    raw = load_port_catalog()
    out: list[PortMethod] = []
    for port in raw["ports"]:
        for method in port["methods"]:
            out.append(
                PortMethod(
                    port_id=port["id"],
                    method=method["name"],
                    tool=method["tool"],
                    slot=method["slot"],
                    status=port["status"],
                )
            )
    return out


def method_for_tool(tool: str) -> PortMethod:
    for row in load_port_methods():
        if row.tool == tool and row.port_id != "route":
            return row
    raise KeyError(f"no reserved port for tool {tool!r}")


def forbidden_import_roots() -> tuple[str, ...]:
    raw = load_port_catalog()
    return tuple(raw["forbidden_imports"])
