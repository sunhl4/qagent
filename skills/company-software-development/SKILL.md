---
name: company-software-development
description: 维护公司科学能力合同、provider 接口和最小造包 profile，不复制科学算法实现。
---

# 公司软件开发

公司科学算法一律在 `company-quantum-platform` 架构下开发：内置组件、领域配方和独立插件共用同一目录与运行端口。不在 Agent 仓复制实现，也不按算法新增 Q-agent 工具。平台通过 `algorithm.catalog` 发布当前 `component_id`，通过 `algorithm.run` 执行可运行标识。Agent 发现走 `quantum_algorithm_catalog`，执行走 `quantum_algorithm_run`。只有公开合同字段变化时才升级 Agent 合同。

开发流程：

1. 在平台仓实现算法或插件，写入平台目录/`company_quantum.plugins.v1`，并保证 HTTP 适配器能把它映射为 `algorithm.catalog` / `algorithm.run`。
2. 在 Agent 侧只在公开 provider 操作或能力描述变化时更新合同。
3. 用 `company-agent-minimal` profile 造包；设备插件必须不存在。
4. 官方 Codex 使用 `permissionMode: never`、`inheritsParentContext: false`。
5. 通过合同测试后再在完整 profile 中做集成验证。
