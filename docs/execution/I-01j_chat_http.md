# I-01j · chat HTTP 不回 session

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P |
| 范围 | `qagent/src/qagent/entrypoints/shell_http.py` · `qagent/tests/test_i01j.py` · `qagent/tests/test_c02f.py`（只改 HTTP 读 session 的断言） |
| 状态 | 代码落地，测绿 |

## 产品锁

- `POST /api/chat` 与 `GET /api/chat/status` 成功响应 **HTTP 无 session_id**。3080 只读 reply / awaiting / cards / ready / open_settings / running / error。
- 仍有：`reply` / `awaiting` / `cards` / `ready` / `open_settings` / `running` / `via`。`pending_approval` 仍只 slim 键（chat 服务已洗）。
- 批准无 token 仍 403，error 形状不变。
- 内部 `turn()` / `chat_status()` 仍可带 session。C-02 租户隔离改用 `load_session_id` + fake prompt 的 sessionId，不从 HTTP 脸读。
- 不算接线。不宣称 G0/G2。句柄仍只三个：`circuit_id` / `asset_id` / `twin_id`。

## 不做什么

不改 `services/chat.py`（`_out` 可继续带 session）。不改 `apps/customer-shell/**` / `models/**` / `run_tests.py` / `PROGRESS.md` / `PARALLEL.md`。不接线 Pennylane。不加第四句柄。不铸 `twin_id`。不 commit。
