# H05 SWE-agent：工具配置、预算和不可信命令

对象 `SWE-agent/SWE-agent`；SHA `3ea751c087f32b16e039a2233dd6eefecef325d5`；提交2026-07-16T11:21:18-04:00；来源 `/tmp/oss-SWE-agent-SWE-agent`。根 LICENSE MIT。本次静态阅读，不据提交日期判断停维。

## 调用链

DefaultAgentConfig 组合模型、模板、ToolConfig、history processors。ToolConfig从bundles读取命令，转换成function-calling工具；Agent用parser把模型回复转成动作，经SWEEnv/SWE-ReX执行，再形成observation。框架有自己的循环，不进入DSH生产。

## 三个关键细节

- `TemplateConfig.max_observation_length=100000` 按字符而非字节，超限模板明确写response clipped。公司科学结果不能复制此裁剪为成功的语义。
- ToolConfig.commands合并bash和bundle，使用tool_sources拒绝重复命令名，错误列出两处来源。可借到公司“合同注册唯一性”测试。
- 默认enable_bash_tool=True，blocklist目的主要避免交互命令，不等于恶意代码隔离。环境变量传播文档明确警告值会出现在debug日志，不能拿来托管公司密钥。

```116:117:sweagent/tools/tools.py
    enable_bash_tool: bool = True
    """Whether to enable the bash tool in addition to the other tools specified in bundles."""
```

## 超时与错误

ToolConfig区分单命令execution_timeout、install_timeout和total_execution_timeout。total超时说明不打断当前命令，仅下一步停止；不能将其理解成硬墙钟取消。
DefaultAgentConfig.max_requeries=3针对格式、blocked action、语法错误重问模型，不等同已派发设备重试。

## 测试

`tests/test_tools_command_parsing.py:6-53` 验证多种签名格式转invoke_format；`:56-78` 验证必填不能排在可选后面及参数名重复报错。它们证明工具声明检查，不证明命令安全。

## 公司映射

1. 保持`contracts/tools.json`唯一工具真源，衍生注册重复即失败。
2. `runtime.js`取消/超时要保留unknown，不把模型重问策略套到QPU提交。
3. 生产preset不能切shell绕过审批，blocklist不能替代受管隔离。
4. `sanitize.py`和诊断门禁保留，环境变量、科学正文不得进入日志。

证据：LICENSE:1-21；agents.py:59-81,149-165；tools.py:29-73,85-91,114-149,166-190；tests/test_tools_command_parsing.py:6-78。未执行上游测试或完整ACI基准。
