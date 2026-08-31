# H-01m · 专用 Agent，不是写死的 H₂ UCCSD

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | 调度落地 |
| 范围 | `packages/qagent-qchem`、`skills/vibe-across-engines`、`skills/h2-uccsd`、`skill-visibility.json`、`adapters/dsh_session.py`、`services/chat.py`、`apps/customer-shell/app.js` |
| 状态 | 完成。人说什么，模型按这句话选公司工具。H₂ UCCSD 仍是可走的一条路，不是唯一反应。不算 G0 过门。 |

## 缺口

H-01l 把 `qchem_run` 描述、lab 技能和欢迎文案推成 H₂ UCCSD。加上 `fold_history` 把上一轮的 `reply` / `circuit_id` 一直带下去，`wait_for_turn` 看见旧回复就立刻返回。对话框里不管说什么都像在出 H₂ 电路图。

## 完成线

- `qchem_run` 仍是公司化学入口。`uccsd_pauli` 只在人点名氢分子 / UCCSD 时用。
- `h2-uccsd` 技能文件还在，lab / sign **不再注入**。
- 欢迎文案不再推销 UCCSD。
- 新的一轮只回这一轮的话。上一轮的 `circuit_id` 不跟到下一句。
- `uccsd_pauli` pin、`GET /api/circuits`、3080 画图、无 body 不回退 H+CX，这些能力还在。
- 活 session `session-6c5022a2-a2d6-4d51-8dfb-dc30071da35f`：人说「我们接了哪些软件？先别上机。」回引擎盘点，脸上 **0** 张 UCCSD 电路图。人再说「要 H2 的 UCCSD 和电路图」，`qchem_run` 出 4 比特 / 194 门并 pin `circuit_id`。
- `qagent/src` 无 `import qchem`。
- 不假 `twin_id`。不算 G0。
