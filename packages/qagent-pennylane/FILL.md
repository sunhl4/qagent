# qagent-pennylane

`PennylanePort` 未接线：不要挂 `PortRegistry`。`execute` 只调 `invoke()`，不要 import 那一家。模拟器禁止第三句柄。见 `qagent/INTERFACES.md`。
