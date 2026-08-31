from __future__ import annotations

from qagent.services.ports import load_port_methods
from qagent.services.registry import default_registry


def main() -> int:
    registry = default_registry()
    print("port\tmethod\ttool\tslot\tstatus")
    for row in load_port_methods():
        bound = type(registry.get(row.port_id)).__name__
        print(f"{row.port_id}\t{row.method}\t{row.tool}\t{row.slot}\t{row.status}\t{bound}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
