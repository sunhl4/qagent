# H-01c / H-01d / H-01e · 3080 气泡对上同一 session

| 日期 | 2026-08-26 |
| 状态 | 代码落地，测绿 |

- `POST /api/chat` → `session.prompt` → `session.history` 折成 reply / cards / running / awaiting。
- `GET /api/chat/status` 短轮询同一 `sessionId`（`.qagent/dsh-session.json`）。
- 批准仍要 `QAGENT_SHELL_TOKEN`；「批准」进**同一** session，不重开黄金路径。
- 3080 显示工具卡，不显示 dsh 工作区门槛。
- `services/chat.py` 不 import `agent`，没有 `_loop`。
