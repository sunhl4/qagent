# H-04f · ELN 手册命中

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | S1 / H-04f |
| 范围 | `qagent/knowledge/manuals/eln.md` · `tests/test_h04f.py` |
| 未改 | `adapters/docs.py` · `qagent/src/**` · `run_tests.py` · `PROGRESS.md` · `test_h04.py` · `test_h04d.py` · `test_h04e.py` · `chat.py` |
| 层 | 第一层造包。检索仍走 `qccd_docs_search` / `WiredDocs`。不是第三套 loop |

## 结论

`QAGENT_KNOWLEDGE_PATH` 指到仓内 `qagent/knowledge` 时，下列查询必中知识根相对 path，`source=knowledge`，摘录 ≤400，`empty` 为假：

| 查询 | 必中 |
|------|------|
| `eln` / `ELN` / `recipe_pin` / `GET /api/eln` | `manuals/eln.md` |

手册写清：ELN 只读 `GET /api/eln`；五类事件 `recipe_pin` / `estimate` / `twin_signoff` / `b3` / `assignment`；fork 丢掉 `twin_id`；无密钥、无电路正文；没有 POST 追加；只有 TwinRun 能发 `twin_id`。手册可提到句柄名，不铸假 `twin_id`。

空临时目录当知识根、查询未命中时：仍诚实（H-04e / H-04d 合同）。不出网。

## 语料

| 路径 | 放什么 |
|------|--------|
| `manuals/eln.md` | ELN 只读 GET / 五类事件 / fork 丢 twin_id / 无 POST |

禁止：实验比特串、secrets、整段 QASM / Pauli、假例子 `twin_id`（`twin_fixture` / `twin_demo` / `twin_leak` / `twin_abc`）、把 CAL / shuttle 当工具。

## 测

```bash
cd /Users/shl/nvidia/qagent && PYTHONPATH=src python3 tests/test_h04f.py
cd /Users/shl/nvidia/qagent && PYTHONPATH=src python3 tests/test_h04e.py
cd /Users/shl/nvidia/qagent && PYTHONPATH=src python3 tests/test_h04d.py
```

## 不做

- 不改 `qagent/src/**`。不改 `docs.py` 摘录合同。
- 不新写 agent loop。不调 `ionstack_twin_run`。
- 不铸 `twin_id`。
- 不 commit。`run_tests.py` / `PROGRESS.md` 留给调度挂测。
