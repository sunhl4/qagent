# I-01e · 预检不回 identity

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P |
| 范围 | `qagent/src/qagent/services/assignment.py` · `qagent/tests/test_i01e.py` |
| 状态 | 代码落地，测绿 |

## 产品锁

- `GET /api/assignments/{id}/preflight` 只回布尔检查，**不回显 identity** / 密钥。
- 载荷只有 `ok` 与 `checks`。`checks` 至少含 `twin_live` / `has_circuit` / `has_asset` 三个布尔。`shots` / `ask_tool` 可留在 checks，不是 identity。
- `ok` 仍是 `live and has_circuit and status==needs_ask`。内部可读 Twin identity 的 `live`，不把 payload（preset / n_qubits / 密钥）塞进 checks，也不回 `token`。
- 句柄仍只三个：`circuit_id`、`asset_id`、`twin_id`。预检载荷里不出现 `twin_id`。不铸 `twin_id`，不假 `accepted:true`。
- 批准路径不动：仍走已有 `approve` / `send("批准")`。不改 `shell_http` 转发，不改 3080 脸（C-01i）。

## 不做什么

不改 `shell_http.py` / `apps/customer-shell/**` / `services/company.py` / `chat.py` / `dsh_session.py` / catalog / `INTERFACES.md`。不接线 Pennylane。不加第四句柄。不宣称 G0/G2 通过。不 commit。`run_tests.py` / `PROGRESS.md` 留给调度挂。
