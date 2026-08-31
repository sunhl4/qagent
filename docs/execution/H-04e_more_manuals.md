# H-04e · 更多手册命中

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | S1 / H-04e |
| 范围 | `qagent/knowledge/manuals/` 增补 · `tests/test_h04e.py` |
| 未改 | `adapters/docs.py` · `run_tests.py` · `PROGRESS.md` · `test_h04.py` · `test_h04d.py` · `chat.py` |
| 层 | 第一层造包。检索仍走 `qccd_docs_search` / `WiredDocs`。不是第三套 loop |

## 结论

`QAGENT_KNOWLEDGE_PATH` 指到仓内 `qagent/knowledge` 时，下列查询必中知识根相对 path，`source=knowledge`，摘录 ≤400，`empty` 为假：

| 查询 | 必中 |
|------|------|
| `list_engines` / 哪些包 | `manuals/list_engines.md` |
| `makespan_ns` / 估计 | `manuals/route_estimate.md` |
| `receipt` / `verify_receipt` | `manuals/receipt.md` |

五包仍是 qdata / qchem / ionstack / route / qiskit；Cirq reserved，不在 `engines[]`。route 估计只有 `makespan_ns`，无签收 `ok`。未签收不是绿封条。手册可提到句柄名，不铸假 `twin_id`。未删 `twinrun_fields.md`。

空临时目录当知识根、查询未命中时：仍诚实（H-04d 合同）。不出网。

## 语料

| 路径 | 放什么 |
|------|--------|
| `manuals/list_engines.md` | 哪些包 / 五包 / Cirq reserved |
| `manuals/route_estimate.md` | route 估计 / `makespan_ns` / 无签收 |
| `manuals/receipt.md` | receipt / `verify_receipt` / 未签收不是绿封条 |
| `manuals/twinrun_fields.md` | 保留。TwinRun 字段用词 |

禁止：实验比特串、secrets、整段 QASM / Pauli、假例子 `twin_id`、把 CAL / shuttle 当工具。

## 测

```bash
cd /Users/shl/nvidia/qagent && PYTHONPATH=src python3 tests/test_h04d.py
cd /Users/shl/nvidia/qagent && PYTHONPATH=src python3 tests/test_h04e.py
```

## 不做

- 不改 `qagent/src/**`。不改 `docs.py` 摘录合同。
- 不新写 agent loop。不调 `ionstack_twin_run`。
- 不铸 `twin_id`。
- 不 commit。`run_tests.py` / `PROGRESS.md` 留给调度挂测。
