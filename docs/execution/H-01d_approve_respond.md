# H-01d · 批准走 dsh 原生 `/api/respond`

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-26 |
| 角色 | A1 |
| 对照源 | DeepSeek Harness `0.1.0-rc.8` · `/Users/shl/nvidia/harness-review/deepseek-harness` |
| 状态 | 代码落地，离线测绿。活 mux 还没对打 |

## 产品锁

- 3080 `/api/chat` 只跟 **同一条** dsh session 说话。
- 「批准」不是另一句 `session.prompt`，更不是 `services.agent._loop`。
- 不铸 `twin_id`。不新建 session。Token 门闩仍在 `shell_http`（本任务未改）。

## RPC（源码合同）

Ask 是 **server-request**，答是 **client-response**。`rpcId` 只回显，不新铸。

| 方向 | 载体 | 形状 |
|------|------|------|
| 运行时提问 | `GET {QAGENT_DSH_URL}/api/events.mux` SSE | `data: {"type":"server-request","rpcId":"…","method":"approval/requested","payload":{"type":"approval/requested","sessionId","approvalId","toolName", callId?, reason?}}` |
| 3080 作答 | `POST {QAGENT_DSH_URL}/api/respond` | `{"type":"client-response","rpcId":"<回显>","result":{"ok":true,"value":{"sessionId","approvalId","outcome":"allowed-once"\|"rejected"}}}` |
| 收据 | HTTP 200 体 | `{accepted:true}` 或 `{accepted:false, reason:"not-pending"\|"bad-response"}` |

历史里还可能出现 `approval/asked`、`approval/decided`、`approval/requested`、`approval/resolved`。`asked` 有 `id`（即 approvalId），**通常没有 mux `rpcId`**。`rpcId` 活在 mux 信封上。

源码锚点（不要抄进产品仓）：

- 信封：`packages/host/apiproxy/src/api/rpc.ts`（`ClientResponse` / `RpcReceipt`）
- 作答：`packages/host/apiproxy/src/api/approvals.ts`
- 路由：`packages/host/apiproxy/src/fetch/handler.ts`（`/api/respond`、`/api/events.mux`）
- 待定表：`packages/host/apiproxy/src/api-proxy.ts` `respond()`

## 已落地

`DshSessionClient`：

- `respond(rpc_id, value)` → `POST /api/respond`。假 transport 走 `transport("respond", {rpcId, value})`，按收据解释。
- `approve_once` / `reject_once` → `allowed-once` / `rejected`。
- `fold_history` 抽出 `pending_approval`：`{rpc_id, approval_id, tool, reason}`；有待定则 `awaiting="approve"`；`approval/resolved`、`approval/decided`、对应 `tool/result` 清掉。
- `snapshot` 带 `pending_approval`（dict 或 `None`）。历史有 ask 但没有 `rpcId` 时，可选 peek mux。
- Peek：`GET /api/events.mux`，短超时（默认 0.4s）。`QAGENT_DSH_MUX=0` 或注入了 transport 则跳过。测例不依赖活 dsh。

`chat.turn`：

- `classify` 已是 approve / reject / run。
- approve / reject：**只读**已存 `sessionId`，禁止 `session.create`，禁止把「批准」当新 prompt。
- 有 pending 且有 `rpcId` → `approve_once` / `reject_once` → `wait_for_turn`。回复必带「同一条 session」和 outcome。
- 没有 pending：诚实「现在没有待批准的上机」，不铸 `twin_id`。

## 仍需活 mux

离线假 transport 已绿。下面必须对着 `dsh --profile qagent`（3081）再打一次：

1. 上机工具触发 `approval/asked` 后，mux 是否立刻重放 `approval/requested`（同一 `rpcId`）。
2. `POST /api/respond` 收据 `accepted:true` 之后，历史是否出现 `approval/decided` / `approval/resolved`，工具是否继续跑。
3. 晚订阅 mux 是否仍用**同一个** `rpcId`（refresh-recovery）。历史页里通常没有这个 id。
4. 并行两个 ask 时，pending 表按 `rpcId` 路由，不能答错条。
5. `urlopen` 读永不结束的 SSE：peek 是短超时尽力读；若首帧慢于 `QAGENT_DSH_MUX_S`，会暂时说「没有 mux rpcId」。需要活实例确认 0.4s 够不够。

没有活 mux 之前，3080 点「批准」在**只有 asked、没有 rpcId** 时会诚实停住，而不会把「批准」丢进 `session.prompt`。
