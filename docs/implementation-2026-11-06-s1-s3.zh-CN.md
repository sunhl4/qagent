# S1–S3 与 Super-agent 接缝（2026-11-06）

本篇落手册第 6.2 到 6.4 节里现在能做的部分，并加上未来上游更新的失败闭合。S4 没有检索源，S5 没有可锁定的上游版本，S6 没有身份和账单 Owner。这三段不开始。

## 适配

`src/company_agent/superagent_adapt.py` 是唯一承认上游事件形状的地方。它要求 `flow_foundation.required_upstream` 仍是 Router、订阅和注意力面板。事件只接受合同里这一版的字段；多出来的字段或 `schema_version` 不是 `1` 就拒绝。没有书面规则时，即使调用方传入 `mode=auto`，也只 `receive`，不开工单。书面规则加上 `auto` 和 `explicit` 才走现有 `evaluate`。GitHub 通道仍然关闭。公司策略不在这里放宽。

Router 仍不在本仓库实现。本地 `subscriptions` 表继续只在开工单时绑定线程。

## S1

`COMPANY_AGENT_RESEARCH_ROOT` 指向绝对目录，并且 `changed_path` 是该目录内 4KB 以内的指标日志时，`company_research_run` 的 `executor` 为 `local`。日志行是 `val_loss=<数字>`。相对基线改进至少 0.02 则保留并停止，否则撤销并继续，直到次数或预算用尽。`timeout` 和无法识别的行记一次崩溃并停止。短账本写在研究状态目录的 `ledger.tsv`，列是实验标识、指标、状态、一句话。工具回执不含日志。

未设置根目录，或路径下没有这份日志时，执行器仍是 `stub`。主目录里的候选日志不改写。工作区根是 Git 仓库时，每一次尝试调用研究层 `createExperimentWorktree`，只把当前候选行写入该次 worktree 的 `changed_path`，并做一次本地提交。撤销时调用 `removeExperimentWorktree`：这次提交后的干净工作树被清掉，脏工作树留下。保留的那一次工作树留在仓库里。不访问远端，不使用凭据，工具回执不含工作树路径。可选的 `baseline_train_time_seconds` 让训练时间均值高出一成的尝试撤销。同一 `attempt` 的多种子相对标准差超过 0.5，或种子数少于 `min_seeds`，停止并要求更换 `changed_path`。

## S2

`resource_type=hpc` 在编译通过后返回 `handoff`。触发正文是 `resource-handoff hpc hpc_submit`。不调用 `hpc_submit`，回执里没有作业号。`resource_type=cloud` 同样只交接，正文是 `resource-handoff cloud quantum_cloud_submit`，不调用 `quantum_cloud_submit`。`qpu` 仍只做真机交接。交接回执带 `resource_type`、`next_tool` 和 `approval_still_required`。这次交接之后，对应的提交工具在 lab 里仍然是询问。

## S3

同一实验上一轮是 `kept` 时，假设和否证都没变的新幂等键返回 `invalid_candidate`，不再跑。运行回执和状态里的 `next_fields` 在交接时写出下一次提交的必填字段：超算是 `job_name,script`，云是 `program_path,target,shots`，真机是 `circuit_id,shots`。其它停止只写下一张卡必须改的字段名：保留、撤销耗尽或旧卡拒绝是 `hypothesis,falsifier`，预算用尽是 `max_cost`，超时、崩溃或种子不稳定是 `changed_path`。`company_research_digest` 在 `lab` 和 `algo` 按租户返回次数、保留、撤销、交接、拒绝、需要人看的停止、失败次数和成本。它不返回假设、日志或路径，也不调用研究层日报的 Markdown。

## 测试

`tests/test_research_clock.py`、`tests/test_superagent_adapt.py`、`tests/test_super_dsh.py`，以及合同、CLI、插件运行时、harness 兼容和回执测试通过。桌面上的一次人工批准仍要人点「允许一次」；这次没有新交超算作业，也没有调用真机。
