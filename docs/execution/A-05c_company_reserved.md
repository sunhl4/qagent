# A-05c · company reserved

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | A-05c |
| 范围 | `services/company.py` · 本笔记 · `qagent/tests/test_a05c.py` |
| 未改 | `engines.py` · `workplace.py` · `catalog.py` · `assignment.py` · customer-shell · `run_tests.py` · `PROGRESS.md` · `PARALLEL.md` · `INTERFACES.md` · `catalog.json` |
| 状态 | `GET /api/company` / `company_payload()` 带 `reserved_engines`。Pennylane 不在 `engines` ids。不算接线。 |

## 行为

| 条件 | 结果 |
|------|------|
| `company_payload()` `engines` | 仍只读 `list_engines()`。五包打头 + cirq。pennylane 不在 ids |
| `company_payload()` `reserved_engines` | 复用 `list_reserved_engines()`。行含 id / kind / label / status（可带 vibe / tools / identity_fields）。`id=pennylane`，`status=reserved`，`kind=interop`。cirq 不在 reserved |
| `GET /api/company`（`shell_http.dispatch`） | 同上。脸仍只用 `legal_name`；本键是目录真源之一 |
| reserved 行 | 不发第三句柄。不铸 `twin_id`。identity 若透传则只有 `circuit_id` + `provenance` |

未接线包标 reserved。不算接线。不要把 Pennylane 写成 wired。不要把 Cirq 写回 reserved。句柄只有 `circuit_id` / `asset_id` / `twin_id`。不发明第四个。不铸第三句柄。源码不 `import pennylane`。不算 G0/G2。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_a05c.py
PYTHONPATH=src python3 tests/test_a05b.py
```

`run_tests.py` `test_company_shell` 未改（engines 五包打头且可变长；加 `reserved_engines` 键仍绿）。`PROGRESS.md` 未改。不 commit。
