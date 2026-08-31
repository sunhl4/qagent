# H-04d · 知识库命中与空库诚实

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | S1 / Q |
| 范围 | `qagent/knowledge/{manuals,specs,patents}` · `tests/test_h04d.py` |
| 未改 | `adapters/docs.py`（H-04c 摘录合同）· `run_tests.py` · `PROGRESS.md` · `test_h04.py` · `chat.py` |
| 层 | 第一层造包。检索仍走 `qccd_docs_search` / `WiredDocs`。不是第三套 loop |

## 结论

`QAGENT_KNOWLEDGE_PATH` 指到仓内 `qagent/knowledge` 时，查询 `TwinRun circuit.body mode shots` 必中 `manuals/twinrun_fields.md`：`source=knowledge`，相对 path，摘录 ≤400，`empty` 为假。内置 `handbooks/` 同时命中可以。知识摘录不含 `twin_id`。

空临时目录当知识根、查询未命中时：`empty` 为真，`detail` 为「知识库是空的。没有这条。」适配器无 urllib / requests / httpx / socket，不出网。不把空客户库假装成手册命中，也不铸第三句柄。

## 语料

| 路径 | 放什么 |
|------|--------|
| `manuals/twinrun_fields.md` | TwinRun 字段用词：`mode` / `shots` / `circuit.body`。不贴电路全文 |
| `specs/handles.md` | 三句柄规范摘要。不写密钥 |
| `patents/public_abstract.md` | 已公开专利摘要。不是申请稿全文 |

禁止：实验比特串、secrets、整段 QASM / Pauli。

## 测

```bash
cd /Users/shl/nvidia/qagent && PYTHONPATH=src python3 tests/test_h04d.py
```

## 不做

- 不改 `docs.py` 摘录合同。
- 不新写 agent loop。不调 `ionstack_twin_run`。
- 不铸 `twin_id`。
- 不 commit。`run_tests.py` / `PROGRESS.md` 留给调度挂测。
