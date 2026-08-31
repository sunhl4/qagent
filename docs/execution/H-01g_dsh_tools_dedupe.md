# H-01g · profile `dsh-tools` 与宿主同一份

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | A1 |
| 范围 | `scripts/start_runtime.sh`、`scripts/bootstrap_wp0.sh` |
| 状态 | 完成。活 dsh 点 `qagent_list_engines` 不再因 `prepare` undefined 崩。不算 G0 过门。 |

## 缺口

3080 已 ready，同一条 session 有「扫氢分子」。模型点了 `qagent_list_engines` 后 `turn/end`：`Cannot read properties of undefined (reading 'prepare')`。

`dsh-agent-loop` 读 `ctx.tools[TOOL_RUNTIME_SCHEDULER].prepare`。profile `node_modules` 里另有一份 `@deepseek-ai/dsh-tools` 时，Symbol 对不上，调度器是 `undefined`。Python `invoke()` 仍通。不改 dsh 内核。

## 完成线

- `start_runtime.sh` / `bootstrap_wp0.sh` 把 `profiles/qagent/node_modules/@deepseek-ai/dsh-tools` 链到宿主 `.pnpm/@deepseek-ai+dsh-tools@*`。
- 两份 realpath 相同。
- 不假 `twin_id`，不编 `accepted:true`。
