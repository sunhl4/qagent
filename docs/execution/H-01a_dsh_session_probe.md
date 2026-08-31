# H-01a · dsh `session.create` / `session.prompt` 探活

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-26 |
| 角色 | A1 |
| 对照源 | DeepSeek Harness `0.1.0-rc.8` · `/Users/shl/nvidia/harness-review/deepseek-harness` |
| 活实例 | `dsh --profile qagent` · `http://127.0.0.1:3081` |

## 结论

**HTTP unary RPC 是产品接线。** 路径、信封、对错码都已对上活进程。`session.list` 成功。`session.create` 被当前 qagent profile 挡住。失败时改 headless **同一棵插件树**，**不许**再写第三套 loop。

## 调用方式（已对照源码 + 活打）

载体：`POST {QAGENT_DSH_URL}/api/{method}`  
默认 `QAGENT_DSH_URL=http://127.0.0.1:3081`  
`Content-Type` 必须是 `application/json`（否则 415）。

请求信封：

```json
{
  "type": "client-request",
  "rpcId": "qagent-<uuid>",
  "method": "session.create",
  "payload": {}
}
```

成功：HTTP 200 +

```json
{
  "type": "server-response",
  "rpcId": "qagent-<uuid>",
  "result": { "ok": true, "value": { "sessionId": "..." } }
}
```

业务失败仍是 HTTP 200，`result.ok=false`，`result.error.code` 有含义。载体失败才是 4xx/5xx。

| 方法 | payload | 成功 value |
|------|---------|------------|
| `session.create` | 至多一个 `workspaceId` **或** `cwd`；可选 `sessionId`、`agentPreset` | `{ sessionId, agentPreset? }` |
| `session.prompt` | `sessionId`、`mode`=`queue`\|`steer`、`content`: `[{type:"text",text}]` | `{ accepted: true }` |
| `session.history` | `sessionId`；可选 `beforeSeq`、`maxMessages` | `{ events, hasMore, projections? }` |
| `session.list` | `{}` | `{ items }` |
| `session.models` | `{ sessionId }` | `{ current, routable, groups, failures }` |

源码锚点（不要复制进产品仓）：

- 信封与路由：`packages/host/apiproxy/src/fetch/handler.ts`
- schema：`packages/host/apiproxy/src/api/sessions.schema.ts`
- 活测写法：`apps/web/tests/smoke-real.e2e.ts` 的 `rpc()`

读历史时只要 `assistant/message` / `user/message` / `tool/result`。`assistant/chunk` 是流，不当最终气泡。

## 2026-08-26 活打记录

| 调用 | 结果 |
|------|------|
| `session.list` `{}` | `ok: true`，`items: []` |
| `host.describe` | `ok`。cwd=`/Users/shl/nvidia/qagent`，provider=`deepseek-official`，model=`deepseek-v4-flash` |
| `agentPreset.list` | stock：`standard`（默认）、`code`、`minimal`、`cordis`。**没有 `qagent`** |
| `session.create` `{agentPreset:"qagent"}` | `agent-preset-not-found` |
| `session.create` `{}` 以及 standard/code/minimal/cordis | `agent-preset-invalid`：`dsh-persona` 再挂 `deployment:persona`，该段已在 host 组合里注册 |

解释：qagent profile 在 **host** 组合已经有 persona。stock agent preset 再 `apply` 一次同名段，create 必炸。这不是 RPC 不通，是 profile 补丁债。

`dsh --profile qagent --help` 在未设 `DSH_HOME` 时会说 profile 不存在。产品启动必须走 `scripts/start_runtime.sh`（它导出 `DSH_HOME=qagent/.dsh-home`）。

## 解法（同日已落地）

空 agent preset `qagent`：`profiles/qagent/agent-presets/qagent/`（`agent.cordis.yml` 为 `[]`）。  
`start_runtime.sh` 把它同步到 `$DSH_HOME/.agent-presets/qagent`。  
`session.create` + `agentPreset=qagent` **已成功**，并得到 `sessionId`。  
`session.prompt` `accepted: true`；`session.history` 能读到 `user/message`。

适配器默认 `QAGENT_DSH_AGENT_PRESET=qagent`。stock preset 仍然不要用。

## 失败策略（计划原文）

1. 先 HTTP unary（本笔记）。  
2. HTTP 通但 create 挂：补 **同一 profile**（注册不重复挂 persona 的 agent preset，或让 stock preset 不再二次注册）。  
3. 仍不行：`dsh --profile qagent` **headless** 同一插件树。  
4. **禁止**把 `services/agent.py` `_loop` 当产品循环。

## 给 H-01b 的合同

- 适配器只讲上述信封。禁止 import `qdata` / `ionstack` / `qchem` / `qiskit`。  
- `QAGENT_DSH_URL` 可测。  
- create / prompt / history 失败都变成诚实中文，不铸 `twin_id`，不跑假 PES。
