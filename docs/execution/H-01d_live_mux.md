# H-01d-live · 对着 3081 记 mux `rpcId`

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | A1 |
| 活实例 | 已在跑的 `dsh --profile qagent` · `http://127.0.0.1:3081` |
| 适配器 | 只用已有 `DshSessionClient`。**未改** `dsh_session.py` |
| 状态 | 活打完成。create 通。mux GET 不是 500。**没有** mux `rpcId`。**没有** `POST /api/respond` |

## 结论

3081 活着。`session.create` + `agentPreset=qagent` 成功。`GET /api/events.mux` 即使带 `Accept: text/event-stream` 仍是 **HTTP 426 Upgrade Required**（`upgrade: websocket`），短超时里看不到 `server-request` / `approval/requested` / mux `rpcId`。无害 prompt 跑完一轮，历史里没有待批准。按合同 **没有** 用编造的 `rpcId` 去 `POST /api/respond`，因此 **没有** 收据 `accepted:true`。没有铸 `twin_id`。没有第三套 loop。

426 不是死进程。活 dsh-web 的 `client-connection` 在进 apiproxy SSE 之前就把 GET mux/host 拦成 WebSocket 升级。`peek_mux_approval()` 把 426 收成 `None`。

## 2026-08-27 活打记录

| 调用 | HTTP | 结果 |
|------|------|------|
| `GET /` | **200** | dsh-web HTML（`content-type: text/html`） |
| `POST /api/session.list` | **200** | `result.ok=true` |
| `POST /api/host.describe` | **200** | cwd=`/Users/shl/nvidia/qagent`，provider=`deepseek-official`，model=`deepseek-v4-flash` |
| `session.create` `{agentPreset:"qagent"}` | **200** | `sessionId=session-1c17bcb4-3c07-4c37-b5f1-ce8e4e741fd5` |
| `GET /api/events.mux`（无 Accept） | **426** | `upgrade required` · `upgrade: websocket` |
| `GET /api/events.mux`（`Accept: text/event-stream`，短超时） | **426** | 同上。**不是 500**。体无 SSE `data:` 帧 |
| `DshSessionClient.peek_mux_approval` | （吞 426） | `None`。**rpcId 未见** |
| `session.prompt` 无害句 | **200** | 这是 prompt 信封的 `accepted: true`，**不是** `/api/respond` 收据 |
| `session.history` / `snapshot` | **200** | reply=`好`；`used_tools=[]`；`pending_approval=None`；`awaiting=None` |
| `POST /api/respond` | **未尝试** | 没有 mux `rpcId`，不编造 |

无害句：`只回复一个汉字：好。不要调用任何工具，不要改文件。`

## 历史里出现过的字符串（不要误读）

本轮 50 条事件。类型有 `approval/policy`、`user/message`、`assistant/message`、`turn/end` 等。**没有** `approval/requested`、`approval/asked`、`server-request`。

| 字符串 | 实际位置 | 不是 |
|--------|----------|------|
| `rpcId` | `user/message` / `agent/inbox/spliced` 的 `source.rpcId`=`qagent-63d55b0823a8` | 不是 mux 信封上的 server-request `rpcId` |
| `approval/policy` | `{"policy":"ask"}` | 不是待批准 ask |
| `twin_id` / `ionstack_twin_run` | `request/header` 系统词里的工具目录 | **没有**铸 `twin_id`，**没有** TwinRun |

`permission/preset`=`workspace-write`。`sandbox/mode`=`workspace-write`。

## 未做

- 不改 `dsh_session.py` / `chat.py` / `shell_http.py` / `run_tests.py` / `PROGRESS.md` / `H-01d_approve_respond.md`。
- 不发明第四句柄。不调 `ionstack_twin_run`。不 `POST /api/respond`。
- 不把 426 写成 SSE 已通，也不把 prompt 的 `accepted:true` 写成批准收据。

## 测

```bash
cd /Users/shl/nvidia/qagent
QAGENT_DSH_URL=http://127.0.0.1:3081 PYTHONPATH=src python3 tests/test_h01d_live.py
```

3081 宕且 `QAGENT_LIVE_MUX` 不是 `1`：打印 skip，退出 0。create 被运行时拒绝：打印精确错误，skip，退出 0。不编造 `accepted:true`。
