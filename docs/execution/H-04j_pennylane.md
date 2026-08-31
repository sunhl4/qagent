# H-04j · Pennylane reserved 手册命中

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | S1 / H-04j |
| 范围 | `qagent/knowledge/manuals/pennylane.md` · `tests/test_h04j.py` |
| 未改 | `adapters/docs.py` · `qagent/src/**` · `run_tests.py` · `PROGRESS.md` · `list_engines.md` · `H-04e_more_manuals.md` · `test_h04e.py` · `test_h04h.py` · customer-shell · 其他 manuals |
| 层 | 第一层造包。检索仍走 `qccd_docs_search` / `WiredDocs`。不是第三套 loop |

## 结论

`QAGENT_KNOWLEDGE_PATH` 指到仓内 `qagent/knowledge` 时，下列查询必中知识根相对 path，`source=knowledge`，摘录 ≤400，`empty` 为假：

| 查询 | 必中 |
|------|------|
| `Pennylane` / `reserved_engines` / `pennylane reserved` | `manuals/pennylane.md` |

手册写清：Pennylane 在 `reserved_engines`；`status=reserved`；`kind` 是互通（interop）；不算已接线；**不在** `engines[]` / `list_engines`；不许发 `twin_id`；源码不要拉 Pennylane 包。手册可提到三句柄名，不铸假 `twin_id`。不写第四句柄字段名。不写 Cirq reserved。不算接线。

空临时目录当知识根、查询未命中时：仍诚实（H-04e / H-04h 合同）。不出网。

## 语料

| 路径 | 放什么 |
|------|--------|
| `manuals/pennylane.md` | reserved_engines / status=reserved / kind 互通 interop / 不算已接线 / 不在 engines[] 与 list_engines / 不许发 twin_id |

禁止：实验比特串、secrets、整段 QASM / Pauli、假例子 `twin_id`（`twin_fixture` / `twin_demo` / `twin_leak` / `twin_abc`）、手册出现 `twin_id=` / `twin_id:` / `import pennylane`、urllib / requests / httpx、把 CAL / shuttle 当工具、把 Pennylane 写成第四句柄、把 Cirq 写成 reserved。

## 测

```bash
cd /Users/shl/nvidia/qagent && PYTHONPATH=src python3 tests/test_h04j.py
cd /Users/shl/nvidia/qagent && PYTHONPATH=src python3 tests/test_h04e.py
cd /Users/shl/nvidia/qagent && PYTHONPATH=src python3 tests/test_h04h.py
```

## 不做

- 不改 `qagent/src/**`。不改 `docs.py` 摘录合同。
- 不改 `list_engines.md`（H-04e 已锁）。不改 `H-04e_more_manuals.md`。
- 不新写 agent loop。不调 `ionstack_twin_run`。
- 不铸 `twin_id`。不 `import pennylane`。
- 不 commit。`run_tests.py` / `PROGRESS.md` 留给调度挂测。
