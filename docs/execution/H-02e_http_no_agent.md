# H-02e · HTTP 不再 import agent

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P / H-02e |
| 范围 | `qagent/src/qagent/entrypoints/shell_http.py` · `qagent/tests/test_h02e.py` · `qagent/tests/test_i01l.py`（只删 reset_agent patch） |
| 状态 | 代码落地，测绿 |

## 产品锁

- 产品 HTTP 不再 import agent。`shell_http.py` 源码无 `qagent.services.agent`、无 `reset_agent`。
- `POST /api/agent/reset` 有 token：只 `reset_chat`（清 dsh session），200 `{"ok": true}`。不再清 deprecated loop 的 thread。
- 无 token / token 不匹配：仍 403，同句 `{"error": "approval requires QAGENT_SHELL_TOKEN"}`，不清 session。
- 服务层 `reset_agent()` 仍在，测试可直接调。产品 HTTP 不再碰它。
- 不算接线。不宣称 G0/G2。句柄仍只三个：`circuit_id` / `asset_id` / `twin_id`。

## 不做什么

不改 `services/agent.py` / `services/chat.py` / `apps/customer-shell/**` / `run_tests.py`。不删 `_loop`。不接线 Pennylane。不加第四句柄。不铸 `twin_id`。不扩第三套 loop。不 commit。`PROGRESS.md` / `PARALLEL.md` 留给调度挂。
