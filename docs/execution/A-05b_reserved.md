# A-05b · reserved 透传

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | A-05b |
| 范围 | `adapters/catalog.py` · `adapters/engines.py` · `services/engines.py` · `services/workplace.py` · `qagent_list_engines.json` · 本笔记 · `qagent/tests/test_a05b.py` |
| 未改 | `catalog.json` · `INTERFACES.md` · `run_tests.py` · `PROGRESS.md` · `PARALLEL.md` · customer-shell |
| 状态 | `invoke` / `workplace_status` 带 `reserved_engines`。Pennylane 不在 `engines` ids。不算接线。 |

## 行为

| 条件 | 结果 |
|------|------|
| `list_engines()` | 仍只读 `catalog.engines`（wired）。五包打头 + cirq。pennylane 不在 ids |
| `list_reserved_engines()` / `load_reserved_packs()` | 读 `catalog.reserved_engines`（缺键则 `[]`）。`id=pennylane`，`status=reserved`，`kind=interop` |
| `invoke("qagent_list_engines")` | `engines` 与上同；另带 `reserved_engines`。cirq 不在 reserved |
| `workplace_status()` | `engines` 仍无 pennylane；同名键 `reserved_engines` 含 id / kind / label / status（可带 vibe） |
| reserved 行 | 不发第三句柄。identity 若透传则只有 `circuit_id` + `provenance`（跟 catalog 一致） |

未接线包标 reserved。不算接线。不要把 Pennylane 写成 wired。不要把 Cirq 写回 reserved。句柄只有 `circuit_id` / `asset_id` / `twin_id`。不发明第四个。不铸第三句柄。源码不 `import pennylane`。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_a05b.py
PYTHONPATH=src python3 tests/test_a05.py
PYTHONPATH=src python3 tests/test_l103_pl.py
PYTHONPATH=src python3 tests/test_iface_pl.py
```

`run_tests.py` / `PROGRESS.md` 未改。不 commit。
