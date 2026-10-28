# P3 批次 B1 执行记录：终止预算（调用次数/墙钟/审批等待）

依据：[约 2000 人天计划](company-agent-2000-person-days-development-plan-v1.0.zh-CN.md) P3「token、调用次数、墙钟、费用和审批等待等终止预算」工作包（25 人天首切片）。本批次不新增工具，给内核加上**按轮（turn）持久化的终止预算账本**：策略允许但轮预算耗尽的调用在派发前被确定性停止。

## 1. 交付

1. 新合同 `contracts/budgets.json`（第 10 份合同，进入 `catalog._CONTRACT_NAMES` 与合同 digest）：轮标识 env `COMPANY_AGENT_TURN_ID`、账本目录 `budgets`（\(\le 262144\) 字节、turn 键 \(\le 512\) 字节）、限额 `invocations=128 / wall_ms=1800000 / approval_waits=16 / device_runs=4 / submissions=16`；任何字段畸形/越界/未知键都使预算检查失效闭合（`load_budgets` 严格校验）。
2. 新内核模块 `src/company_agent/budget.py`：
   - 账本按 **subject + turn** 联合哈希命名（`turn_<sha256 前缀>`），原始 turn 标识永不落盘；存放在回执存储根的 `budgets/` 下，与回执同一可信持久化位置。
   - `precheck`（派发前）在三个维度失效闭合：总调用次数、累计墙钟、per-tool 子限额（真机 4 次/轮，云/HPC 提交 16 次/轮）；`precheck(wait=True)` 管审批等待次数。
   - `charge`/`charge_approval_wait` 尽力而为（账本 I/O 失败只保证响应不受污染），预检永远先于任何派发；被策略拒绝的调用一概不记账。
   - 未声明 turn 的宿主回退到进程内「process」桶：单个 CLI 子进程天然新一轮，宿主后续声明 turn id 即获得跨调用持久预算（DSH 只需设置 env，kernel 无需接线）。
3. `invoke.py` 接线：决策之后、派发之前 `precheck`；`needs_ask` 先记账一笔审批等待；allow/ask-approved 的执行路径（含 ok 与 error 两类结果）按实测墙钟记账。未知工具、校验失败与策略拒绝发生在记账点之前，不消耗预算。
4. 合规门禁（18 → **19**）：`denied / turn-budget-invocations-exhausted`——账本轮直写耗尽后，`invoke` 必须返回 error 且零 dispatch 回执，证明「预算耗尽即停止派发」。

## 2. 验证（不含全量前的定向）

- 新增 `tests/test_budgets.py` **14 项**：合同形状、7 类畸形变异失效闭合、账本按 turn 命名隔离与 turn 标识不出现在路径/正文、subject 隔离、两个子限额与审批等待限额失效闭合、墙钟边界（注入 150ms > 100ms 合同）、invoke 计费与拒绝不记账、invocations 耗尽时 invoke 返回 error。
- 全套合同/策略/回执/门禁定向绿；`docs/evidence/compliance-local.json` 重生成 19/19 ok，合同 digest 随新合同更新。
- ruff 对全部触碰文件无告警；期间顺手确认 `tests/` 在 `test_no_legacy` 中新增第 10 份合同文件钉。

## 3. 边界（诚实的不完整）

- 预算维度当前覆盖：调用次数、墙钟、审批等待、真机/提交子限额；**token/费用记账**要等 P7 计费接入同一账本（模型 token 费用和 HPC/QPU 用量按计划分账，本批次只留好账本形状）。
- turn id 由宿主（DSH）声明；在宿主接入前，跨进程预算不生效（每 CLI 子进程独立计数，仍然安全但弱）。
- 审批等待记账只统计「进入人工审批」事件，不统计审批等待墙钟时长。
