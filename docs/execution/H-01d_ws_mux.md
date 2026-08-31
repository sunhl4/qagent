# H-01d-ws · mux peek 走 WebSocket

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | A1 |
| 对照源 | DeepSeek Harness · `/Users/shl/nvidia/harness-review/deepseek-harness` |
| 锚点 | `packages/client/connection/src/websocket-downlink.ts` · `packages/client/connection/src/index.ts` |
| 适配器 | `qagent/src/qagent/adapters/dsh_session.py`（`peek_mux_approval` / `_http_mux` / `_ws_mux`） |
| 状态 | 离线测绿。426 GET **不是**成功。无帧则 `None` |

## 为什么 GET 是 426

活 dsh `client-connection` 把网络 `GET /api/events.mux`（和 `/api/events.host`）拦成 **HTTP 426** `upgrade: websocket`。没有 SSE 回退。下行在 `websocket-downlink.ts`：升级 `/api/events.mux`，泵 JSON 文本帧 `{type:"server-request", rpcId, method, payload}`。客户端在这条 socket 上发业务帧是协议违规（close 1008）。作答仍是 **HTTP POST `/api/respond`**。Unary 仍是 `POST /api/{method}`。

## 已落地

- `peek_mux_approval`：注入了 transport 或 `QAGENT_DSH_MUX=0` → **不联网**，回 `None`。
- 先 `GET /api/events.mux`。**426 不当成功**（不解析 `upgrade required` 当 `rpcId`）。
- 426 之后短连 `ws://{QAGENT_DSH_URL host}/api/events.mux`。`Host` 用 URL 的 loopback 权威（默认 `127.0.0.1:3081`），好过信任围栏。
- 短窗口读文本帧。包成 `data: …` 走已有 `parse_mux_sse`，或直接 `parse_mux_json`。只抽已出现的 `approval/requested` `rpcId`。
- 无帧 / 超时 → `None`。**不铸** `rpcId`，**不**用编造的 id 去 `POST /api/respond`，**不**写 `accepted:true`，**不铸** `twin_id`。
- 标准库 RFC6455 客户端。不在 socket 上发消息。不新开第三套 loop。

## 未做

- 不改 `chat.py` / `agent.py` / `shell_http.py` / `run_tests.py` / `PROGRESS.md` / `test_h01d_live.py` / `H-01d_live_mux.md`。
- 不把 respond 搬到 WebSocket。不发明第四句柄。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_h01d.py
PYTHONPATH=src python3 tests/test_h01d_ws.py
```

3081 宕：`test_h01d_ws` 的活打项 skip。空 mux 没有 `rpcId` **不算失败**。
