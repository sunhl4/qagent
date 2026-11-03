# P6-A / P8-A 执行记录（2026-10-29）

对应执行计划：`docs/company-agent-execution-plan-2026-10-29.zh-CN.md`。

## P6-A 工作台任务投影

- 在 `apps/company-workspace/host.mjs` 增加受认证保护的 `/company-workspace/workbench/tasks` 只读端点。
- 端点通过 `company-agent reconcile` 读取持久回执，只处理 `cloud.submit`、`hpc.submit`、`device.run`。
- 按 `request_id`、时间戳和记录类型折叠旧事件；旧事件不能覆盖新事件。
- 只有成功结果同时具备 `completed` 状态和合法平台业务引用时，才显示为 `completed`；其他情况保持 `unknown` 或 `refused`。
- 结果状态、计费状态与执行状态分开投影；P7 尚未完成，因此计费状态固定为 `not_projected`。
- 资源中心“作业与回执”页读取该端点；端点不可用时显示服务不可用，不创建空的成功任务。
- 未增加合同工具、模型循环、会话循环、自动重试或前端权限来源。

## P8-A 网页注入隔离

- 在 `scripts/compliance_gate.py` 增加 `web-injection-never-authorizes` 场景。
- 页面文本同时包含覆盖指令、工具调用、凭据泄露和身份冒充内容时，只生成四类不可信信号。
- 该文本不会改变 `boot` 的 deny 或 `lab` 的 ask 决策，不创建 dispatch 回执，也不进入授权参数。
- 既有 `tests/test_web_fetch.py` 的网页端到端信号测试继续通过；未把启发式检测当作安全结论。

## 验证

- `node --check apps/company-workspace/host.mjs`：通过。
- `node --check apps/company-workspace/client.js`：通过。
- `corepack pnpm --dir tests/ui test`：31 通过、1 跳过；真实 DSH 云生命周期因本地 Python sidecar 不可用而按测试设计跳过。
- `python -m pytest tests/test_web_fetch.py tests/test_compliance_report.py tests/test_no_legacy.py tests/test_verify_dsh_profiles.py -q`：48 通过、1 排除。
- `python docs/validate_2000_person_days_plan.py`：计划算术和硬边界通过。
- `python scripts/compliance_gate.py`：26/26 通过，证据写入 `docs/evidence/compliance-local.json`。
- 全量 `python -m pytest -q`：1114 通过、31 失败、17 跳过、49 排除。失败项集中在既有跨平台 UTF-8 读取、Office 工具计数同步、DSH 子进程取消/sidecar 和真实 Overleaf/插件环境，不属于本批 P6/P8 定向失败；这些项目保留为后续 E0/E3 与发布前回归项。

## 未完成边界

- P6-B 的四状态轴、断线恢复、重复事件和跨客户端一致性尚未完成。
- P7 计费仍等待财务/平台字段样例。
- P4 真实云/HPC/QPU 事实源和 P1 企业 IdP 仍等待 Owner 输入。
- 全量 Python 回归的 31 个失败项已登记为独立收尾范围：Windows 文件读取统一显式 UTF-8、Office 工具计数断言同步、DSH 子进程取消与 sidecar 环境、真实 Overleaf/插件环境复验。它们不改变 E1/E2 的定向出口，也不能被本地门禁绿替代。
