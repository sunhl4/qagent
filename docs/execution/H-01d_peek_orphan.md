# H-01d-peek-orphan · 历史孤儿 ask 时 snapshot 补 peek

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | A1 |
| 适配器 | `qagent/src/qagent/adapters/dsh_session.py`（只动 `snapshot` 与两个小 helper） |
| 状态 | 离线测绿。无帧则 pending 仍是 `None`。本包**不声称**活收据 `accepted:true` |

## 为什么

活 3081 上 ask 常常只出现在 mux。历史可以有 `ionstack_twin_run` + `awaiting=approve`，但 `pending_approval is None`（没有 `approval/requested` 事件，也就没有 `rpc_id`）。旧 `snapshot` 只在历史上已经有 pending dict、且缺 `rpc_id` 时才 peek。孤儿情况下聊天点「批准」会走到「现在没有待批准的上机」，即使 WS peek 能看见真的 `approval/requested`。

## 已落地

- `snapshot`：历史在等批准，且 `pending_approval` 为 `None` **或** 缺 `rpc_id` → 调用已有 `peek_mux_approval(session_id)`。
- peek 对该 session 回了真 pending → 合并已出现的 `rpc_id` / `approval_id` / `tool` / `reason` / `call_id`。**不铸**这些 id，**不铸** `twin_id`。
- peek 为 `None` / mux 空 / 426 后无帧 / 超时 → 快照原样留下。诚实。不铸 pending，不 `POST /api/respond`。
- 注入了 `transport` 或 `QAGENT_DSH_MUX=0` → **不联网**（peek 已有此门）。
- mux WebSocket 只读。作答仍是 HTTP `POST /api/respond`。不新开第三套 loop。

## 未做

- 不改 `chat.py` / `agent.py` / `shell_http.py` / workplace / assignment / `policy.json` / customer-shell / `run_tests.py` / `PROGRESS.md` / `test_h01d_live.py` / `H-01d_live_mux.md` / `qagent-eval.yml`。
- 不把「批准」改成另一句 `session.prompt`。不发明第四句柄。
- 本包没有对着活 3081 打出 `/api/respond` 收据，**不写**活 `accepted:true`。

## 测

```bash
cd /Users/shl/nvidia/qagent
QAGENT_DSH_MUX=0 PYTHONPATH=src python3 tests/test_h01d.py
PYTHONPATH=src python3 tests/test_h01d_ws.py
PYTHONPATH=src python3 tests/test_h01d_orphan.py
```

空 mux 没有 `rpcId` **不算失败**。
