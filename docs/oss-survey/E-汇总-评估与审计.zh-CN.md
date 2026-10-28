# E 册更新：评估与观测

详见 [逐项目复核索引](reviewed/README.zh-CN.md)：08 Cline、41 Promptfoo、42 Inspect、43 SWE-bench、44 simple-evals、45 Vivaria、54 Langfuse、55 Phoenix、56 AgentOps、57 OTel 语义约定。

## 撤回与更正

- 公司已有策略文件和输出预算，不能直接换成通配符审批、五值权限或 16KB 截断；科学结果超限不能裁剪后冒充完整。
- 评估端工具调用修复与多别名解析用于生成/判定测试输入，不进入生产严格信封。
- Inspect 自动生成的 Compose 模板不能证明所有自定义沙箱都默认断网。
- Langfuse/OTel 是观测模型，不能自动保证可靠审计、身份认证、账单或业务作业事实。认证 Session 与 TraceSession 分开理解。
- OTel MCP `params._meta` 中的 trace context 注入是正常遥测传播，不是恶意提示注入攻击示例。
- Cline 的自动批准 UI 不是公司设备授权位，云端同样保留 ask/deny 硬约束。

## 测试面定位

确定性合同门禁、模型效果判分、端到端界面测试及真实平台验收分层实施。外部评估框架可在隔离测试面使用，不成为生产 Agent 循环；远程生成与遥测需独立审查。详见 [本地架构对照](03-本地架构对照与工程边界.zh-CN.md) 和 [工程衔接](04-工程衔接建议.zh-CN.md)。
