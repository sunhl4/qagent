# 公司 Super DSH 产品计划

日期：2026-11-04。全公司只有一个 DSH 运行时。架构说明见 [super-dsh-architecture.zh-CN.md](super-dsh-architecture.zh-CN.md)。2026-11-06 起，技术手册、产品方向和分阶段开发计划见 [super-dsh-handbook-2026-11-06.zh-CN.md](super-dsh-handbook-2026-11-06.zh-CN.md)。2026-11-10 起，开发桌面的会话预设是上游 `standard`，公司工具和批准留在档案插件，以手册第 3 节为准。Company Agent 的 2000 人天基线仍描述 P 系列产品化，不在本计划里重算。

## 已证实

- 控制面、执行面、平台时钟三个面已经写进 `contracts/superagent.json`。执行面只有现有的 DSH 会话，没有第二套运行时。
- 平台信号只产生候选触发。它不开工单，也不调用设备。
- 账本角色是 `local-control-plane`，`company_fact_store` 为假。SQLite 执行本地控制面规则，不是全公司事实源。
- 研究层契约留在 `research-layer/contracts/`。默认装配仍是 `adapters/stub/`。
- 设备策略不变：`lab` / `sign` 询问，`boot` / `algo` 拒绝。句柄仍只有 `asset_id`、`circuit_id`、`twin_id`。

## 本轮补上

- 幂等键保存载荷指纹。同一租户、同一键、同一指纹返回原来的触发。来源、主体、正文或 `policy_version` 不同则拒绝，不返回旧触发。
- 同一触发最多一张未结束工单，并由数据库唯一约束守住。工单结束后，下一次 `mode=auto` 且 `strength=explicit` 的评估才可以新开。`observe` 和 `off` 只记决策。
- 会话绑定只在引用仍为空时写入。同一指派不能改绑到另一会话。
- `unknown` 执行可以查询，不能重新提交。`reconcile` 只把它结案为 `ended`，不换会话，也不把它改回 `running`。
- `receive`、`evaluate`、`recover`、`note_execution`、`reconcile` 必须带 `tenant_id`。找不到记录和跨租户读取使用不同错误。幂等冲突保留自己的错误，不收成一句笼统拒绝。
- `github` 和 `feishu` 在通道关闭时拒绝写入。开放来源是 `company`、`workspace`、`research`。调用方传入的 `schema_version` 不是 `1` 时拒绝。
- 公司翻译层实现研究层 `ComputePort`。信封保留 `cpu`、`gpu`、`hpc`、`cloud`、`browser`。未知、超时、未决、排队和运行中的状态可以查询，不可以重新提交。
- `qpu` 只生成设备审批交接，字段是租户、请求标识、幂等键、`mandate=lab` 和 `quantum_device_run`。控制面把它记成候选触发，不开工单，不调用设备。
- 工单执行只保存 `dsh:` 会话引用和公司工具包名称。同一指派不能改绑到另一会话。会话正文、科学结果和密钥不能写入。`recover` 只把这组短字段读回来，不返回触发正文或报告。
- 进程内去重只属于当前适配器实例。`degraded: true` 时，本阶段通过 `HP-02`、`HP-05`、`CL-01`。`HP-01`、`HP-03`、`HP-06`、`MD-01` 记为 blocked。身份、对象存储和会话用例不由这个适配器冒充。

## 仍等待 Owner

- 真实云、HPC、模型、QPU 窗口、企业身份和账单仍对应执行计划 E5–E8，以及研究层决策请求单。本地测试不代表这些窗口已经接通。
- GitHub、飞书保持关闭，直到各自有独立的 Source 合同。
- 全公司多租户事实源、审计和保留期仍未选定。当前账本不能升成那一层。
- 报价、日志、模型正文、真实作业状态要等对应 Owner。blocked 用例不能提前标成通过。

## 不变式

- DSH 是唯一 Agent Runtime。控制面不开模型循环、会话循环或工具循环。
- Mandate 只有 `boot`、`lab`、`algo`、`sign`。设备执行继续是 `lab` / `sign` 询问，`boot` / `algo` 拒绝。
- 句柄只有 `asset_id`、`circuit_id`、`twin_id`。只有 `ionstack-twinrun` 可签发 `twin_id`。
- 平台时钟不能直接开工单，也不能直接调用设备。`signal` 只产生候选触发。
- `unknown` 执行可以查询，不能重新提交。结案只走 `reconcile`。Watchdog 不能改策略、预算或租约。
- 根目录 `contracts/` 与 `research-layer/contracts/` 不合并。研究层不写第二套云 SDK、Slurm 客户端或模型网关。
- GitHub、飞书保持关闭，直到各自有独立的 Source 合同。未确认的外部输入沿用研究层决策请求单的默认立场，不用本地测试冒充生产完成。

## 现在不能做的接法

- 不在研究层里直接 import `company_agent.hpc_ssh` 或 `providers`。端口语义会被 SSH 和 HTTP 细节污染，以后换调度器就要改实验代码。
- 不把平台信号的正文、命令、环境变量或密钥写进工单账本。
- 不把当前 SQLite 账本当成全公司多租户事实源。它可以执行本地控制面规则，但公司事实源仍要等租户、审计和保留期决策。
- 不把 2000 人天基线改写成新的容量估算。

## 目标接缝

控制面事件带 `schema_version`、`tenant_id`、`source`、`idempotency_key`、`subject_id`、`mandate`、`policy_version`。同一租户、同一幂等键、同一载荷指纹返回原来的触发。载荷不同则失败。同一触发只有一张未结束工单。跨租户读取失败闭合。

研究层继续调用自己的 `ComputePort` 和 `ModelGatewayPort`。`research-layer/adapters/company-agent/` 实现 `ComputePort`，默认不替换 stub：

- 研究层 `idempotencyKey`、`tenantId`、`requestId` 映射到公司 provider 信封里的同一组标识，并保留资源种类。
- 未知、超时、未决、排队和运行中的状态可以查询，不可以重新提交。
- `qpu` 生成设备审批交接。控制面只记录候选触发，不调用 `quantum_device_run`。
- 适配器声明 `degraded: true`。真实云、HPC、模型、QPU 窗口、企业身份和账单仍等待 Owner，对应执行计划 E5–E8。报价、日志和模型正文在此之前保持 blocked。

工单执行只保存 DSH 会话引用和工具包名称。会话正文、科学结果和密钥不进控制面。

## 交付顺序

1. 本文件，以及研究层里仍把根目录写成“看不见的 harness-core”的前提。
2. `contracts/superagent.json` 的控制面字段，并同步账本、工具 schema 和测试。`signal` 继续只记录候选触发。
3. 公司适配器的状态映射和一致性测试。此阶段不连接真实云、HPC 或模型。
4. 安全类用例 `HP-02`、`HP-05`、`CL-01` 已作为准入。真实作业、报价、日志和模型正文仍 blocked，stub 继续是默认。
5. Temporal、GitHub、飞书和多团队生产化放在端口稳定之后。
