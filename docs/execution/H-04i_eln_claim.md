# H-04i · ELN 拒铸手册命中

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | S1 / H-04i |
| 范围 | `qagent/knowledge/manuals/eln.md` · `tests/test_h04i.py` · `docs/execution/H-04i_eln_claim.md` |
| 未改 | `adapters/docs.py` · `qagent/src/**` · `run_tests.py` · `PROGRESS.md` · `H-04f_eln_manual.md` · `test_h04f.py` · customer-shell · 其他 manuals |
| 层 | 第一层造包。检索仍走 `qccd_docs_search` / `WiredDocs`。不是第三套 loop |

## 结论

`QAGENT_KNOWLEDGE_PATH` 指到仓内 `qagent/knowledge` 时，下列查询必中知识根相对 path，`source=knowledge`，摘录 ≤400，`empty` 为假：

| 查询 | 必中 |
|------|------|
| `claim_blocked` / `cirq_claim_twin_id` | `manuals/eln.md` |

手册在原五类之外写上 `claim_blocked`：短 reason 可见（例如 Cirq 拒铸）。仍只读 `GET /api/eln`，没有 POST。保持 H-04f 锁句。手册可提到句柄名，不铸假 `twin_id`。不写第四句柄字段名。不算过门。

空临时目录当知识根、查询未命中时：仍诚实（H-04f / H-04h 合同）。不出网。

## 语料

| 路径 | 放什么 |
|------|--------|
| `manuals/eln.md` | 只读 GET / 五类 + `claim_blocked` / 短 reason / `cirq_claim_twin_id` / 无 POST |

禁止：实验比特串、secrets、整段 QASM / Pauli、假例子 `twin_id`（`twin_fixture` / `twin_demo` / `twin_leak` / `twin_abc`）、手册出现 `twin_id=` / `twin_id:` / urllib / requests / httpx、把 CAL / shuttle 当工具、把拒铸写成第四句柄。

## 测

```bash
cd /Users/shl/nvidia/qagent && PYTHONPATH=src python3 tests/test_h04i.py
cd /Users/shl/nvidia/qagent && PYTHONPATH=src python3 tests/test_h04f.py
cd /Users/shl/nvidia/qagent && PYTHONPATH=src python3 tests/test_h04h.py
```

## 不做

- 不改 `qagent/src/**`。不改 `docs.py` 摘录合同。
- 不改 `H-04f_eln_manual.md`。不改其他 manuals。
- 不新写 agent loop。不调 `ionstack_twin_run`。
- 不铸 `twin_id`。
- 不 commit。`run_tests.py` / `PROGRESS.md` 留给调度挂测。
