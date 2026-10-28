# 57项目源码复核索引

更新：2026-10-22。固定范围为57个独立项目，伴随迁移仓及历史标签不重复计数。

每篇记录完整提交SHA、源代码路径、具体机制、测试证据/缺口及公司适用边界。**“逐项复核”指所声明子系统的静态源码研究，不指完整仓库安全审计、上游测试已运行或组件已接入公司平台。** 各篇覆盖深度不同，不再按篇数推断全框架深读程度。

机器证据：[项目清单](projects.json)、[运行时对照证据](evidence-runtime.json)、[工具/知识证据](evidence-tools.json)、[本轮补齐证据](evidence-platform-additions.json)。各证据文件固定SHA及行范围；复现时在GitHub用`仓库/blob/完整SHA/相对路径`查看相同源文件，避免main分支漂移。`/tmp/oss-*`只是本机本次快照位置，不是长期存档保证。

阅读顺序：[总报告](../05-复核总报告.zh-CN.md) → [本地架构对照](../03-本地架构对照与工程边界.zh-CN.md) → [工程衔接](../04-工程衔接建议.zh-CN.md) → [验证记录](../06-验证记录.zh-CN.md)。

## 01–19：运行时对照与协议

<a id="project-01"></a>
### 01 · sst/opencode
[权限求值、缺失agent拒绝和审批生命周期](H01-opencode.zh-CN.md)。研究permission服务，不引入其Runtime。

<a id="project-02"></a>
### 02 · gptme/gptme
[确认hook、上下文作用域及无hook默认行为](H02-gptme.zh-CN.md)。默认确认与公司失败闭合不同。

<a id="project-03"></a>
### 03 · block/goose
[批准存储、参数关联与撤销反例](H03-goose.zh-CN.md)。本地原子写入不等于审计不可篡改。

<a id="project-04"></a>
### 04 · All-Hands-AI/OpenHands
[跨端事件与远程审批桥](H04-openhands.zh-CN.md)。应用账号和运行时session是不同认证域。

<a id="project-05"></a>
### 05 · SWE-agent/SWE-agent
[工具配置、命令重复与预算](H05-swe-agent.zh-CN.md)。blocklist不等于强隔离。

<a id="project-06"></a>
### 06 · SWE-agent/mini-swe-agent
[预算、错误成本和轨迹出口](H06-mini-swe-agent.zh-CN.md)。不移植其执行循环。

<a id="project-07"></a>
### 07 · Aider-AI/aider
[符号图排名与缓存新鲜度](H07-aider.zh-CN.md)。检索排名不授予源码读取权限。

<a id="project-08"></a>
### 08 · cline/cline
[消息与检查点映射](H08-cline.zh-CN.md)。本地检查点不能回滚外部作业。

<a id="project-09"></a>
### 09 · huggingface/smolagents
[代码工具与执行器生命周期](H09-smolagents.zh-CN.md)。导入限制不是操作系统沙箱。

<a id="project-10"></a>
### 10 · pydantic/pydantic-ai
[延期工具结果与批准关联](H10-pydantic-ai.zh-CN.md)。不采用approve_all作为设备授权。

<a id="project-11"></a>
### 11 · letta-ai/letta
[迁移到letta-code后的记忆围栏](H11-letta.zh-CN.md)。迁移仓单独固定SHA，不重复计数。

<a id="project-12"></a>
### 12 · openai/openai-agents-python
[Guardrail并行默认及取消清理](H12-openai-agents.zh-CN.md)。检查最终输出不能补救已发生副作用。

<a id="project-13"></a>
### 13 · google/adk-python
[函数声明、参数校验与确认](H13-google-adk.zh-CN.md)。容错过滤与严格合同拒绝不同。

<a id="project-14"></a>
### 14 · mastra-ai/mastra
[工具schema、issues优先与错误格式](H14-mastra.zh-CN.md)。日志截短不是脱敏。

<a id="project-15"></a>
### 15 · langchain-ai/open-swe
[数据库事件claim及并发限额](H15-open-swe.zh-CN.md)。MIT；去重不是设备exactly-once。

<a id="project-16"></a>
### 16 · jlowin/fastmcp
[STDIO授权区别与结果截断](H16-fastmcp.zh-CN.md)。协议框架可候选，治理仍在公司入口。

<a id="project-17"></a>
### 17 · modelcontextprotocol/python-sdk
[handler注册与工具/协议错误](H17-mcp-python-sdk.zh-CN.md)。采用当前源码布局，不沿用旧路径。

<a id="project-18"></a>
### 18 · modelcontextprotocol/typescript-sdk
[输入输出校验和冷缓存限制](H18-mcp-typescript-sdk.zh-CN.md)。alpha快照及许可迁移需单独评估。

<a id="project-19"></a>
### 19 · modelcontextprotocol/servers
[文件根、符号链接与覆写竞态](H19-mcp-servers.zh-CN.md)。仅复核filesystem，不泛化全部servers。

## 20–39：工具治理、Skills、隔离与知识

<a id="project-20"></a>
### 20 · modelcontextprotocol/inspector
[OAuth状态丢失与发行方错配](H20-mcp-inspector.zh-CN.md)。适合开发期诊断，不公开管理端。

<a id="project-21"></a>
### 21 · invariantlabs-ai/mcp-scan
[扫描会执行包及调用远端分析](H21-mcp-scan.zh-CN.md)。不是纯本地静态lint。

<a id="project-22"></a>
### 22 · github/github-mcp-server
[AST验证ReadOnlyHint显式声明](H22-github-mcp-server.zh-CN.md)。元数据齐全不是只读行为证明。

<a id="project-23"></a>
### 23 · docker/mcp-gateway
[Noop默认放行与策略部署边界](H23-mcp-gateway.zh-CN.md)。不能依赖默认client完成公司授权。

<a id="project-24"></a>
### 24 · Qiskit/mcp-servers
[IBM Runtime账户、后端选择与作业接口](H24-mcp-quantum-server-ecosystem.zh-CN.md)。只借协议思路，不在Agent导入科学包。

<a id="project-25"></a>
### 25 · barvhaim/qiskit-mcp-server
[全局线路、部分修改和全量counts反例](H25-mcp-unofficial-server.zh-CN.md)。**未识别许可证及自动测试，保留缺口，不建议复制集成。**

<a id="project-26"></a>
### 26 · anthropics/skills
[格式验证、渐进装载与分技能许可](H26-anthropic-skills.zh-CN.md)。validator独立单测未识别，文档技能不能统称Apache。

<a id="project-27"></a>
### 27 · obra/superpowers
[会话hook与宿主特定JSON输出](H27-superpowers.zh-CN.md)。技能脚本同样需要准入。

<a id="project-28"></a>
### 28 · e2b-dev/E2B
[SDK网络规则与凭据占位](H28-e2b.zh-CN.md)。客户端配置不证明服务端已强制执行。

<a id="project-29"></a>
### 29 · microsandbox/microsandbox
[网络engine、profile及拒绝语义](H29-microsandbox.zh-CN.md)。目标WSL/服务器隔离未运行验收。

<a id="project-30"></a>
### 30 · daytonaio/daytona
[私有化声明及v0.190.0历史SDK](H30-daytona.zh-CN.md)。当前私有核心不在复核范围。

<a id="project-31"></a>
### 31 · dagger/container-use
[单客户端假设与进程内environment](H31-container-use.zh-CN.md)。不能直接推广为企业多租户。

<a id="project-32"></a>
### 32 · openinterpreter/Open-Interpreter
[当前Rust/Codex fork的批准动作](H32-open-interpreter.zh-CN.md)。纠正旧Python/AGPL描述。

<a id="project-33"></a>
### 33 · cloudflare/agents
[持久调度、时间边界与默认重试](H33-cloudflare-agents.zh-CN.md)。三次重试不适用于设备提交。

<a id="project-34"></a>
### 34 · mem0ai/mem0
[身份元数据保护与缓存scope](H34-mem0.zh-CN.md)。主体ID由宿主提供，非模型自报。

<a id="project-35"></a>
### 35 · getzep/graphiti
[group分区与多种时间过滤](H35-graphiti.zh-CN.md)。字段存在不等于默认过滤过期资料。

<a id="project-36"></a>
### 36 · topoteretes/cognee
[PGVector schema与engine所有权](H36-cognee.zh-CN.md)。共享连接关闭和prune需单独回归。

<a id="project-37"></a>
### 37 · langchain-ai/langgraph
[checkpoint、pending写入与恢复排序](H37-langgraph.zh-CN.md)。会话恢复不是外部事务回滚。

<a id="project-38"></a>
### 38 · microsoft/LLMLingua
[压缩模型、远程代码默认与语义损失](H38-llmlingua.zh-CN.md)。合同/审批/线路不做有损压缩。

<a id="project-39"></a>
### 39 · yamadashy/repomix
[确定顺序收集与整文件读取预算](H39-repomix.zh-CN.md)。maxFileSize不是读前内存硬上限。

## 40–57：入库、评估、产品界面、模型与观测

<a id="project-40"></a>
### 40 · mendableai/firecrawl
[注入分类器及fail-open分支](H40-firecrawl.zh-CN.md)。网页始终是数据，不成为授权来源。

<a id="project-41"></a>
### 41 · promptfoo/promptfoo
[评测中的宽容MCP别名规范化](H41-promptfoo.zh-CN.md)。生产信封继续严格拒绝。

<a id="project-42"></a>
### 42 · UKGovernmentBEIS/inspect_ai
[策略升级链、拒绝记录及预算](H42-inspect-ai.zh-CN.md)。评测框架不作为第二生产Runtime。

<a id="project-43"></a>
### 43 · SWE-bench/SWE-bench
[零执行、skip与矛盾退出码](H43-swe-bench.zh-CN.md)。未运行不能被判成功。

<a id="project-44"></a>
### 44 · openai/simple-evals
[小型评测接口、聚合及报告](H44-simple-evals.zh-CN.md)。评分分母与缺失样本须明确。

<a id="project-45"></a>
### 45 · METR/vivaria
[首错保留、finally清理和资源归属](H45-vivaria.zh-CN.md)。MIT，评测环境清理不能撤销QPU副作用。

<a id="project-46"></a>
### 46 · open-webui/open-webui
[工具ACL、MCP交互与品牌例外](H46-open-webui.zh-CN.md)。本次范围未识别直接行为单测，全局MCP隔离仍需验证。

<a id="project-47"></a>
### 47 · danny-avila/LibreChat
[部署开关、角色权限和上传入口](H47-librechat.zh-CN.md)。局部unknown=true不能移植公司执行层。

<a id="project-48"></a>
### 48 · CopilotKit/CopilotKit
[实际运行实例通知与连接状态](H48-copilotkit.zh-CN.md)。只借前端协议/显示，不引入其循环。

<a id="project-49"></a>
### 49 · continuedev/continue
[HTTP上下文请求字段与错误边界](H49-continue.zh-CN.md)。路径本地过滤不代表完整输入不外发。

<a id="project-50"></a>
### 50 · ollama/ollama
[本地/云分支及消息截断](H50-ollama.zh-CN.md)。公司现有模型服务优先，不强制替换。

<a id="project-51"></a>
### 51 · ggml-org/llama.cpp
[模板条件、grammar/schema与工具测试](H51-llama-cpp.zh-CN.md)。测试辅助函数、注释项与实际执行覆盖分开。

<a id="project-52"></a>
### 52 · vllm-project/vllm
[请求验证、模板信任与token预算](H52-vllm.zh-CN.md)。模型推理队列不替代HPC/QPU调度。

<a id="project-53"></a>
### 53 · berriai/litellm
[预算主体、规范名称及窗口计数](H53-litellm.zh-CN.md)。模型用量hook不是公司财务账本。

<a id="project-54"></a>
### 54 · langfuse/langfuse
[业务TraceSession、项目隔离与去重](H54-langfuse.zh-CN.md)。观测存储不等于不可变审计。

<a id="project-55"></a>
### 55 · arize-ai/phoenix
[OTel exporter配置与分区许可](H55-phoenix.zh-CN.md)。主体ELv2与独立埋点包Apache不同。

<a id="project-56"></a>
### 56 · AgentOps-AI/agentops
[动态JWT、header保护及导出失败](H56-agentops.zh-CN.md)。遥测退避不适用于设备重投。

<a id="project-57"></a>
### 57 · open-telemetry/semantic-conventions
[MCP上下文传播及GenAI迁移规范](H57-otel-semconv.zh-CN.md)。伴随仓单独锁版；追踪context injection不是提示注入。

## 完成口径与后续门禁

源文件存在、范围合法、版本固定、摘录逐字一致，只证明证据可复现。完整语义覆盖、测试有效性、依赖供应链、许可证使用场景及真实产品集成仍需独立审查。缺失上游测试或许可时明确保留warning，不用虚构证据换取绿色状态。

公司下一步按[工程衔接建议](../04-工程衔接建议.zh-CN.md)推进统一账号授权、审批关联、作业对账和结果模板；本轮没有修改业务配置、读取凭据或连接真实模型/云/HPC/QPU。
