# Company Agent 合同 2.0 迁移

日期：2026-10-08。对应 `contracts/tools.json`、`contracts/results.json` 2.0.0；能力版本统一 2.0，HTTP 外层信封仍为 `company-agent-provider/1.0`。这是破坏兼容的工具语义迁移，不接受在旧同版本上默默增加必填字段。发布须同步 Python、DSH 插件和合同，按受管发布流程重启新会话；本轮实施不重启用户当前运行时。

## 算法目录与运行

目录身份为 `(id, version)`，二者分别是平台 `component_id` 与精确组件版本。同 ID 的多版本可以并存，按二元组排序。运行必须提供 `algorithm`、`component_version`、`catalog_version`；前两者原样取自同一目录条目，第三个原样取自该次目录响应。禁止猜版本或隐式 latest。目录分页由平台绑定快照和查询条件，旧快照被拒绝后重新查询，结果未知不自动重跑。

`input_schema` 是平台发布的可选机器参数合同，支持的 JSON Schema 子集以 Agent 的 `schema.py` 为准；根必须封闭 object。未提供机器合同的目录条目只提供展示提示，不能据此推断执行能力。参数校验、预算、可信执行注册与授权均由平台在执行前重验。发现、可运行声明、请求身份认证和执行授权是不同边界。平台默认不为目录中全部条目注册执行器。

## 统一结果边界

所有工具共享文本内容检查：明显私钥标记、完整 OpenQASM 标记及当前已配置凭据原值回显被拒绝。provider 继续应用字段/句柄/结构预算，禁止静默截断后伪装成功。本地工作流的绑定元数据不是科学句柄产出，因此不套用 provider 的嵌套句柄黑名单；仍执行各自封闭 schema。知识引用可解释设备来源术语，但不能携带禁止正文。

凭据检查仅在进程内读取声明的 provider token 环境值及常用模型 API key 值用于拒绝回显，不记录、不导出。它不保证识别任意未知或编码后的秘密。知识资料仍须事先脱敏、授权；检索结果带 `trust=untrusted_reference_data`，资料中的指令不得覆盖系统规则。知识检索检查完整读入文档，拒绝在未选片段藏有禁止正文的污染语料。

Python 与 JavaScript 对所有 JSON 数值统一拒绝非有限值、负零和超出安全整数范围的整数值；精确大整数应按平台 schema 使用十进制字符串，不静默舍入。

## 工作流外部输入

`inputs` 为最多 32 个 `{id,handle,value}` 对象；`handle` 只允许既有三类句柄，value 前缀必须匹配。输入 ID 唯一，不能与步骤 ID 冲突。

消费步骤仍在 `needs` 声明类型；绑定用 `{input: 输入ID, output: 句柄类型}` 或 `{step: 前序步骤ID, output: 句柄类型}`，二选一，不能同时存在。只有同类型来源唯一时可推断。外部输入不计为新产出，`asset.list` 也不伪称创造资产。服务端存在性、归属和审批仍须真正调用时检查，静态校验不会执行任务。

## 科学短摘要

算法、资产读取与电路导出可含 `summary.metrics`，结构为 `schema_version=scientific-metrics/1.0` 及最多 8 个 items。每项严格限定 name、kind、value、unit。kind 为 objective、uncertainty、probability、count；单位只允许 dimensionless、hartree、eV、second、count；值有限且限制在正负一万亿内。概率必须无量纲且在 0–1，计数必须为非负整数和 count 单位，不确定度必须非负，名字不能重复。字段不是开放字典，不返回 Pauli、样本或电路正文。指标属于哪项科学任务、估计方法与可复现性由平台内部资产绑定，短摘要不替代完整内部记录。

## 可观测性与能力发现

每次调用产生一个最终 invocation 诊断；provider 另外记录派发前和结束事件。统计派发次数只数 `event=provider,status=started,execution_state=dispatched`，不能把最终事件重复计数。预校验失败的 request_id 为空，未知工具名称用固定 unknown，错误类型是稳定 `error_category`，不会记录参数、URL、正文或凭据。坏合同可能使标准诊断编码器不可用，CLI 仍诚实返回固定合同错误，不伪造有效合同摘要。

`company_capabilities` 返回 preset；每个能力同时包含全量 tools、当前 visible_tools、provider_state（local/unconfigured/configured_unverified）。配置不等于健康探测或服务验收。

## 验收与限制

本地门禁、双仓回环服务与无科学执行替身证明工程合同；真实科学正确性、真实模型、浏览器批准参数对照、生产部署和设备对账须人工监督。现行阶段说明见 `super-dsh-handbook-2026-11-06.zh-CN.md`。历史 1.x 文稿已退出仓库，不充当当前 2.0 验收证据。
