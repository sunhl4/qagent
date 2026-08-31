# H-04g · 租户隔离手册命中

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | S1 / H-04g |
| 范围 | `qagent/knowledge/manuals/tenant.md` · `tests/test_h04g.py` |
| 未改 | `adapters/docs.py` · `qagent/src/**` · `run_tests.py` · `PROGRESS.md` · `test_h04.py` · `test_h04d.py` · `test_h04e.py` · `test_h04f.py` · `chat.py` · customer-shell |
| 层 | 第一层造包。检索仍走 `qccd_docs_search` / `WiredDocs`。不是第三套 loop |

## 结论

`QAGENT_KNOWLEDGE_PATH` 指到仓内 `qagent/knowledge` 时，下列查询必中知识根相对 path，`source=knowledge`，摘录 ≤400，`empty` 为假：

| 查询 | 必中 |
|------|------|
| `租户` / `隔离` / `?tenant=` / `X-QAGENT-TENANT` | `manuals/tenant.md` |

手册写清：空租户见全部且不带头；客户脸用 `?tenant=`，请求头带租户；已设租户看不见别人的交办和实验记录；对话应当分开 session。不宣称过门。手册可提到句柄名，不铸假 `twin_id`。不写第四句柄字段名。

空临时目录当知识根、查询未命中时：仍诚实（H-04e / H-04d 合同）。不出网。

## 语料

| 路径 | 放什么 |
|------|--------|
| `manuals/tenant.md` | 租户隔离 / 空租户不带头 / `?tenant=` / 请求头 / 交办与实验记录 / session 应当分开 |

禁止：实验比特串、secrets、整段 QASM / Pauli、假例子 `twin_id`（`twin_fixture` / `twin_demo` / `twin_leak` / `twin_abc`）、把 CAL / shuttle 当工具、把租户写成第四句柄。

## 测

```bash
cd /Users/shl/nvidia/qagent && PYTHONPATH=src python3 tests/test_h04g.py
cd /Users/shl/nvidia/qagent && PYTHONPATH=src python3 tests/test_h04f.py
cd /Users/shl/nvidia/qagent && PYTHONPATH=src python3 tests/test_h04e.py
```

## 不做

- 不改 `qagent/src/**`。不改 `docs.py` 摘录合同。
- 不新写 agent loop。不调 `ionstack_twin_run`。
- 不铸 `twin_id`。
- 不 commit。`run_tests.py` / `PROGRESS.md` 留给调度挂测。
