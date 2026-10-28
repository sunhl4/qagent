# H57 OpenTelemetry语义约定：追踪传播不是提示注入

对象 `open-telemetry/semantic-conventions`；SHA `0eb883be629282ae400a8063492626ff14dfb62f`，提交2026-10-21T20:38:52+00:00；来源 `/tmp/oss-open-telemetry-semantic-conventions`。其GenAI文档已迁移，因此补充实际规范来源 `open-telemetry/semantic-conventions-genai`，SHA `9ffc7e00c639be7712e544e3e54331e885dccf84`，提交2026-10-21T19:06:47+00:00；本地 `/tmp/oss-otel-semconv-genai`。伴随仓库不增加57项目计数。两者许可分别核对根LICENSE；本轮只做规范静态复核，不运行collector。

## 实际规范链及纠错

主仓库`docs/gen-ai/mcp.md`是迁移说明，不是完整现行规范。伴随仓库的MCP约定仍标Development；以固定提交审查，不能把最新文档称作长期稳定协议。

MCP基于JSON-RPC，HTTP追踪上下文只覆盖传输请求，不足以区分流内多个MCP消息。规范建议在`params._meta`传播配置的OTel context，接收端提取作为remote parent；W3C的traceparent/tracestate/baggage使用不带DNS前缀的键。

```52:57:docs/gen-ai/mcp.md
Instrumentations SHOULD propagate context using the configured
[OpenTelemetry propagators](https://opentelemetry.io/docs/specs/otel/context/api-propagators/)
by injecting it into the MCP request
[`params._meta`](https://modelcontextprotocol.io/specification/2025-11-25/basic#_meta)
property bag when creating a request or notification. The receiver extracts the
context from `params._meta` and uses it as the remote parent.
```

这里的inject是标准追踪上下文注入，**不是prompt injection攻击**。追踪标识也不应被当作身份凭证：跨租户传播需受限，baggage不能携带密钥或任意用户敏感信息。

规范建议仅在能可靠识别外层GenAI工具执行span时合并，避免重复；这不是禁止创建全部MCP span。HTTP与MCP上下文独立，可通过links关联。URI默认不进span名称以控制基数，也有助于避免泄漏资源路径；仍需对属性进行允许清单控制。

## 测试证据及局限

伴随仓库`docs/gen-ai/non-normative/tests/test_schemas.py:1-9,47-54,109-115`提供JSON schema及错误快照测试；验证示例与schema变更，不是MCP客户端真实传播或后端租户隔离测试。本轮未运行，MCP端到端trace连续性仍需专门集成验收。

## 公司适配

先定义允许的模型/工具耗时、错误类别、审批决策和关联标识，再由宿主适配到OTel；禁止原始prompt、完整科学结果、密钥和内部代码正文。开发中的规范字段封装在适配层，避免直接固化成公司业务合同。

OTel负责观测，不负责企业审批、计费真相或设备exactly-once。`diagnostics.py`的短诊断继续保留，若扩展持久审计，应明确独立存储与完整性策略，而不是把trace成功上报当作已经商业验收。

证据范围：主仓库`docs/gen-ai/mcp.md:5-11`；伴随仓库同路径`:43-65,103-113,134-155`；上述schema测试；两仓库根LICENSE。规范示例不等于运行结果。
