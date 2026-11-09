# Company Agent 开发规则

## 真源

1. `contracts/`：工具、能力、provider、策略和 preset。
2. `src/company_agent/`：合同内核和南向适配器。
3. `packages/`：DSH 插件，只注册工具并转调 `company-agent invoke`。
4. `profiles/`：DSH 组合，不包含业务逻辑。
5. `tests/`：目标架构门禁。

## 硬规则

- DSH 是唯一 Agent Runtime；禁止新增模型循环、会话循环或工具循环。
- 上游 Super-agent 的流程是控制面基座，Router、订阅和注意力面板是这条流程的必要部分，用来承接大量任务和没有人逐条输入的任务。这些能力消费上游实现，不在公司仓库里再写一套路由器或会话循环。锁定前，`company_work_item` 只保存同一对象链的薄替身，订阅只记录工单和线程的对应。无人输入的任务从 Source 事件进入，没有书面规则时只记录；书面规则打开工单后，超算、云和真机仍走公司策略。公司长期保留工具包、审批策略和平台时钟。
- 不直接 import `company_quantum_platform` 或任何科学算法包。
- 算法名单只来自 `company-quantum-platform` 的 `algorithm.catalog`；标识是平台 `component_id`，禁止在 Agent 代码或知识库固化算法列表。
- 句柄只有 `asset_id`、`circuit_id`、`twin_id`。
- 只有 `quantum_device_run` 且 provider 为 `ionstack-twinrun` 时可返回 `twin_id`。
- `quantum_device_run` 在 `lab` / `sign` 必须 ask，在 `boot` / `algo` 必须 deny。
- 官方 Codex 使用 `permissionMode: never` 和 `inheritsParentContext: false`；只注册宿主 provider，不挂载模型可见的 Codex 委派工具，因此无法获得设备工具。
- 生产 profile 关闭 DSH 内置 preset 和用户可写 preset 根，只允许项目管理的 system-trust `company-agent` 组合，禁止创建或切到带 shell 的编码 preset 绕过审批。
- 未知工具、未知 preset、缺失 provider、坏信封全部失败闭合。
- 工具结果必须短；禁止 CAL、shuttle、bitstrings、Pauli 全文、密钥和完整电路正文。
- 修改工具 schema 时同步合同测试和 DSH 注册。

## 开发顺序

先改合同，再改 Python adapter，再改 DSH 插件，最后改测试。不得为通过旧测试恢复旧工具名。
