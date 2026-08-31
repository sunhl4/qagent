# H-04c · qccd_docs_search 短摘录合同

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-26 |
| 角色 | S1 |
| 工具 | `qccd_docs_search` · `qagent/src/qagent/adapters/docs.py` |

## 合同

- 命中 `text` 是短摘录，上限 400 字；优先取查询首次命中附近窗口，不是整文件前 1200 字。
- 每条命中带 `path`（相对该根）和 `source`（`handbook` \| `knowledge`）。
- 只读本地 `.md` / `.txt`。适配器无 urllib / requests / httpx / socket，不出网。
- 未命中：`{hits: [], empty: true, detail: ...}`。不得用 `handbooks/twin_run.md` 顶替未命中查询。
- 内置手册仍参与检索：TwinRun / `mode` / `shots` / `circuit.body` 必中（`run_tests.py` 的 `test_docs_empty`）。
- 最多 8 条，避免灌模型。

## 空库

外部知识根为空时，手册关键词仍可命中内置 `handbooks/`。查询本身未命中时诚实返回空，不把 `twin_run.md` 当默认替身。

## 测

```text
PYTHONPATH=src python3 tests/test_h04.py
PYTHONPATH=src python3 tests/run_tests.py
```
