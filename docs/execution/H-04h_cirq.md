# H-04h · Cirq 互通手册命中

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | S1 / H-04h |
| 范围 | `qagent/knowledge/manuals/cirq.md` · `tests/test_h04h.py` |
| 未改 | `adapters/docs.py` · `qagent/src/**` · `run_tests.py` · `PROGRESS.md` · `list_engines.md` · `H-04e_more_manuals.md` · `test_h04e.py` · `test_h04g.py` · customer-shell |
| 层 | 第一层造包。检索仍走 `qccd_docs_search` / `WiredDocs`。不是第三套 loop |

## 结论

`QAGENT_KNOWLEDGE_PATH` 指到仓内 `qagent/knowledge` 时，下列查询必中知识根相对 path，`source=knowledge`，摘录 ≤400，`empty` 为假：

| 查询 | 必中 |
|------|------|
| `Cirq` / `interop` / `provenance=cirq` | `manuals/cirq.md` |

手册写清：Cirq 已在 `engines[]`；`kind` 是互通（interop）；`provenance=cirq`；不是我们的机器；不许发 `twin_id`；源码不要拉 Cirq 包。手册可提到三句柄名，不铸假 `twin_id`。不写第四句柄字段名。不算 G0/G2/G3 过门。

空临时目录当知识根、查询未命中时：仍诚实（H-04e / H-04g 合同）。不出网。

## 语料

| 路径 | 放什么 |
|------|--------|
| `manuals/cirq.md` | Cirq 已在 engines[] / kind 互通 interop / `provenance=cirq` / 不是我们的机器 / 不许发 twin_id |

禁止：实验比特串、secrets、整段 QASM / Pauli、假例子 `twin_id`（`twin_fixture` / `twin_demo` / `twin_leak` / `twin_abc`）、手册出现 `twin_id=` / `twin_id:` / `import cirq`、urllib / requests / httpx、把 CAL / shuttle 当工具、把 Cirq 写成第四句柄。

## 测

```bash
cd /Users/shl/nvidia/qagent && PYTHONPATH=src python3 tests/test_h04h.py
cd /Users/shl/nvidia/qagent && PYTHONPATH=src python3 tests/test_h04e.py
cd /Users/shl/nvidia/qagent && PYTHONPATH=src python3 tests/test_h04g.py
```

## 不做

- 不改 `qagent/src/**`。不改 `docs.py` 摘录合同。
- 不改 `list_engines.md`（H-04e 已锁）。不改 `H-04e_more_manuals.md`。
- 不新写 agent loop。不调 `ionstack_twin_run`。
- 不铸 `twin_id`。
- 不 commit。`run_tests.py` / `PROGRESS.md` 留给调度挂测。
