from __future__ import annotations

from dataclasses import dataclass, field

from qagent.adapters.catalog import NativeCatalog
from qagent.adapters.cirq import WiredCirq
from qagent.adapters.codex import WiredCodex
from qagent.adapters.docs import WiredDocs
from qagent.adapters.ionstack import WiredIonstack
from qagent.adapters.pin import NativePin
from qagent.adapters.qchem import WiredQChem
from qagent.adapters.qdata import WiredQData
from qagent.adapters.qiskit import WiredQiskit
from qagent.adapters.route import WiredRoute


@dataclass
class PortRegistry:
    catalog: NativeCatalog = field(default_factory=NativeCatalog)
    pin: NativePin = field(default_factory=NativePin)
    qdata: WiredQData = field(default_factory=WiredQData)
    qchem: WiredQChem = field(default_factory=WiredQChem)
    ionstack: WiredIonstack = field(default_factory=WiredIonstack)
    route: WiredRoute = field(default_factory=WiredRoute)
    qiskit: WiredQiskit = field(default_factory=WiredQiskit)
    cirq: WiredCirq = field(default_factory=WiredCirq)
    docs: WiredDocs = field(default_factory=WiredDocs)
    codex: WiredCodex = field(default_factory=WiredCodex)

    def get(self, port_id: str) -> object:
        try:
            return getattr(self, port_id)
        except AttributeError as exc:
            raise KeyError(f"unknown port {port_id!r}") from exc


def default_registry() -> PortRegistry:
    return PortRegistry()
