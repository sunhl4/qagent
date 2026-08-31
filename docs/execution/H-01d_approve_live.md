# H-01d-approve-live · 活 mux 批准诚实记录

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | Q · H-01d-approve-live |
| 活实例 | 已在跑的 `dsh --profile qagent` · `http://127.0.0.1:3081` |
| 脑 | 不是第三套 loop。脑是已经在跑的 `dsh --profile qagent` |
| 适配器 | 只用已有 `DshSessionClient.peek_mux_approval`。**未改** `dsh_session.py` |
| 状态 | 笔记落地。活 `accepted:true` **未证明** |

## 产品锁

- 不是第三套 loop。3080 的脑是已经在跑的 `dsh --profile qagent`（3081）。
- 作答是 HTTP `POST /api/respond`，体为 `{type:client-response, rpcId, result.value:{sessionId,approvalId,outcome:allowed-once\|rejected}}`。
- `rpcId` **只回显** mux 已经出现的值。**禁止铸造** `rpcId`。禁止铸造 `twin_id`。
- Mux `GET /api/events.mux` 是 **HTTP 426** `upgrade: websocket`。peek 走已实现的 WebSocket 短读。客户端不得在 mux socket 上发业务帧。
- 空 mux / 未见 `rpcId`：**不许** `POST /api/respond`，**不许**把 `accepted:true` 写成已完成。空 mux 是诚实成功，**不是** H-01d 活批准已通。

## 活 `accepted:true` 规则

活 `accepted:true` **未证明**（unproven），除非 mux 回显了真实 `rpcId`，并且 `POST /api/respond` 把**那一个** `rpcId` 原样回显、dsh 收据为 `accepted:true`。没有回显就写 `accepted:true` 是造假。本笔记不把空 mux、426、或 `session.prompt` 信封里的 `accepted: true` 当成批准收据。

## 2026-08-27 本轮记录

对着已在跑的 3081 实打（`QAGENT_LIVE_MUX=1`）。create 通。peek 是 `None`。

| 调用 | HTTP | 结果 |
|------|------|------|
| `GET /` | **200** | dsh-web 活着 |
| `session.create` `{agentPreset:"qagent"}` | **200** | `sessionId=session-6c777498-42c3-4dc3-87f1-12854bbc5cf0` |
| `GET /api/events.mux` | **426** | `upgrade: websocket`。体 `upgrade required`。不是 SSE 成功 |
| `session.prompt` 无害句 | **200** | 信封 `accepted: true`，**不是** `/api/respond` 收据 |
| snapshot | **200** | reply=`好`；`pending_approval=None`；`awaiting=None` |
| `peek_mux_approval` | （WS 短读） | **未见 rpcId**（`None`） |
| `POST /api/respond` | **未尝试** | 没有可回显的 mux `rpcId`，不编造 |
| 批准收据 | **未写** | 活 `accepted:true` 仍未证明 |

无害句：`只回复一个汉字：好。不要调用任何工具，不要改文件。`

本轮未见 mux `server-request` / `approval/requested`。按合同 **没有** `POST /api/respond`，因此 **没有** 把 `accepted:true` 写成已完成。没有铸 `twin_id`。没有在 mux socket 上发业务帧。没有调 `ionstack_twin_run`。空 mux 是诚实成功，不是 H-01d 活批准通过。

## 未做

- 不改 `dsh_session.py` / `chat.py` / `agent.py` / `shell_http.py` / `run_tests.py` / `PROGRESS.md` / `test_h01d.py` / `test_h01d_ws.py` / `test_h01d_live.py` / `H-01d_ws_mux.md` / `H-01d_live_mux.md` / customer-shell。
- 不发明第四句柄。不铸 `rpcId`。不把 426 写成已通。
- 默认测例只读本笔记；活探函数存在，但除非 `QAGENT_LIVE_MUX=1` 否则不调用。

## 测

```bash
cd /Users/shl/nvidia/qagent
QAGENT_DSH_MUX=0 PYTHONPATH=src python3 tests/test_h01d.py
PYTHONPATH=src python3 tests/test_h01d_approve_live.py
```

活探（可选，且 3081 必须活着）：

```bash
cd /Users/shl/nvidia/qagent
QAGENT_LIVE_MUX=1 PYTHONPATH=src python3 tests/test_h01d_approve_live.py
```

3081 宕、或 `session.create` 被拒：诚实 skip，退出 0。peek 为 `None`：记录「未见 rpcId」，不 POST，不写 `accepted:true`。空 mux 是诚实成功，不是 H-01d 活批准通过。
