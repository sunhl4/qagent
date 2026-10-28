# F 册更新：前端与模型服务

详见 [逐项目复核索引](reviewed/README.zh-CN.md)：46 Open WebUI、47 LibreChat、48 CopilotKit、49 Continue、50 Ollama、51 llama.cpp、52 vLLM、53 LiteLLM。

## 更正后的选型原则

- 公司已有本地模型、成熟云平台/HPC；Ollama、llama.cpp 和 vLLM 是候选服务方式，不要求三者串联。LiteLLM 也是可选代理而非必建依赖。
- `genTruncate` 一类输入上下文处理不能当作输出 token 上限；结构化生成不代替业务 schema、单位、权限及句柄校验。
- LiteLLM 模型预算不代替 QPU/HPC 的资源计费和最终结算，平台继续是业务账单事实源。
- UI 状态订阅只能改善展示与同步，不构成授权。三栏工作台、网页端和桌面端仍共用受管后端事实，右栏由 DSH 运行。
- Open WebUI 品牌条款包含适用条件和例外，不能笼统说任何修改都必须购买许可。CopilotKit 目录存在也不能作为功能验收依据。

下一步应先验证现有模型端点的工具调用、流式取消、并发、结构化结果和错误语义；再按真实缺口决定依赖。具体工作见 [工程衔接](04-工程衔接建议.zh-CN.md)，许可细节见各固定版本复核稿。
