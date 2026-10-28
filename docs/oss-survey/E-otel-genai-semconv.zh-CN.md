# OTel GenAI 语义约定调研更新入口

请阅读 [57 — OpenTelemetry 语义约定及 GenAI 迁移仓复核](reviewed/README.zh-CN.md#project-57)。规范来源、Development 稳定性、字段与传播语义分别固定版本记录。

明确更正：MCP 示例中的 injected trace context 是正常 W3C 追踪上下文传播，不是恶意提示注入。业务 provider 与模型 provider 不混用，完整参数/科学正文不默认入 span，观测也不自动承担审批账本。

详情见 [纠错记录](02-纠错记录.zh-CN.md) 与新稿。附属规范仓不重复增加项目计数。
