---
name: quantum-workflow
description: 规划并验证公司量子工作流，正确传递句柄并对设备执行请求人工批准。
---

# 量子工作流规划

使用 `company_workflow_validate` 先验证结构化工作流。`valid:true` 仅表示结构和静态参数有效，不表示服务可用、资产存在、当前 preset 允许执行或人工已批准；验证本身不执行步骤。

同一类型可有多个上游输出。消费步骤必须用 `bindings.circuit_id = {step: "export_a", output: "circuit_id"}` 明确来源；旧 `needs` 只有唯一上游时才能省略 binding。引用仅指向此前明确声明的输出，自引用和未来引用无效；实际调用时仍传服务返回的三种科学句柄。

推荐顺序：

用户已有的句柄通过 `inputs: [{id: "existing", handle: "circuit_id", value: "circ_…"}]` 声明，消费步骤可用 `bindings.circuit_id = {input: "existing", output: "circuit_id"}` 绑定。多个同类输入或输出必须明确选择，外部输入不计为工作流新产出。服务端仍检查归属与存在性。

1. `quantum_algorithm_catalog` 向 `company-quantum-platform` 查询当前组件目录。`id` 是平台 `component_id`，不要编造算法名。
2. 只对目录中 `runnable` 为 true 的精确条目调用 `quantum_algorithm_run`：`algorithm` 原样使用该条目的 `id`，`component_version` 原样使用 `version`，`catalog_version` 原样使用同一目录响应的快照版本。禁止省略版本或猜测 latest。参数遵守平台 `input_schema`；目录过期应重新查询，不自动重跑未知结果。成功后产生 `asset_id`，必要时同时产生 `circuit_id`。
3. 若只有 `asset_id`，用 `quantum_circuit_export` 获取注册后的 `circuit_id`。
4. 可选 `quantum_simulate` 做独立模拟验证。
5. 可选 `quantum_compile_estimate` 做独立编译估算。
6. 仅在人明确要求设备执行时调用 `quantum_device_run`，并等待 ask。

不得编造第四个句柄。模拟器和编译器不得产生 `twin_id`。不要把平台内部算法实现复制到 Agent，也不要在知识库固化算法名单。新算法、重构算法和插件算法都只在 `company-quantum-platform` 注册；Agent 只维护对该框架的目录与运行接口。

设备发送后若超时、断连、取消或报告 `unknown`，应说明执行结果未知并停止自动重试。取消等待不等于设备停止；保留短 `request_id` 供服务运维核对。新的设备调用仍需新的人工批准，不能把关联 ID 当幂等保证。
