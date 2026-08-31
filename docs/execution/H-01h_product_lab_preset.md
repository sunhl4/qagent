# H-01h · 产品 3081 默认 lab

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | A1 |
| 范围 | `scripts/start_runtime.sh`、活 `.qagent/active_preset` |
| 状态 | 完成。产品脑默认 lab。活 session `4122615b` 点了 `qchem_run` / `qdata_run_recipe(a2_chem_pes)`，无 `qagent-policy`。算出 `asset_fc9f7d82f5d4`。不算 G0 过门。 |

## 缺口

H-01g 后「扫氢分子」能点 `qagent_list_engines`。活 `active_preset` 被写成 `sign`，3081 启动默认仍是 `algo`。文件赢过环境，`qchem_run` / `qdata_run_recipe` / `qdata_list_assets` 回 `Error: qagent-policy`。不改政策表，不改 dsh 内核。

## 完成线

- `start_runtime.sh` 在 source `dsh.env` 之后 `QAGENT_PRESET:-lab`。显式 `algo` 仍留给造包。
- 启动时把 `active_preset` 写成本次 `QAGENT_PRESET`，清掉测留下的 `sign`。
- `qdata_run_recipe` 无 `name` 在 lab 仍 deny；`name=a2_chem_pes` 才 allow。
- 活复验：3080 发「扫氢分子」，session `session-4122615b-3554-461e-b7e1-38788be9db29`。`qdata_run_recipe` 回 `asset_id=asset_fc9f7d82f5d4` / `run_93db2f77b293` / `source=qdata-cli`。全文无 `qagent-policy`。
- 不假 `twin_id`，不编 `accepted:true`。不算 G0。模型随后在 `qdata_sandbox_exec` 里空转，那是下一刀，不是本包。
