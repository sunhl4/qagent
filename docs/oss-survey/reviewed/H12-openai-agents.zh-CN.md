# H12 OpenAI Agents Python：Guardrail 与运行边界复核

- 项目：`openai/openai-agents-python`。
- SHA：`841dfdd938bfd4ca052475eb76d6245a356868e0`。
- 提交：2026-10-22T00:26:59+00:00。
- 来源：`/tmp/oss-openai-openai-agents-python`。
- 许可：根 `LICENSE:1-21`，MIT。
- 验证：静态实现与测试阅读，未运行模型或上游测试。

## 范围与定位

本项目提供完整 Agent SDK，而非仅协议库。
本次沿 guardrail 的数据类型、执行器、异常传播和测试核对安全边界。
公司不能整体引入其 Runner，因为 DSH 是唯一生产运行时。
可借鉴的是结果归档、异步清理以及安全检查和执行的先后关系。

## 调用链

应用声明 `InputGuardrail` 或 `OutputGuardrail`。
装饰器最终包装用户提供的 guardrail 函数。
`InputGuardrail.run()` 验证函数可调用，再兼容同步和异步返回值。
返回值装为 `InputGuardrailResult`，包含规则实例和 `GuardrailFunctionOutput`。
内部执行器创建任务，收集结果，遇到 tripwire 时触发停止和异常语义。
流式路径还将结果写进运行结果累积器与队列，最后由 Runner 消费。
证据：`src/agents/guardrail.py:19-130`、`run_internal/guardrails.py:31-111`。

## 一：结果是结构化的，不是“模型说拒绝”

`GuardrailFunctionOutput` 分开存任意 output_info 和布尔 tripwire。
`InputGuardrailResult` 明确绑定是哪条规则产生哪份结果。
这比解析自然语言里的“拒绝”更可测，也便于单独记录规则结果。
但 output_info 是 Any，不自动符合公司的短结果、脱敏和有限字段合同。
公司若借鉴结构，必须收缩为白名单数据，不能直接把完整输入和解释写进 trace。
证据：`guardrail.py:19-45`。

## 二：默认并行检查不是设备执行前权限门

`InputGuardrail.run_in_parallel` 默认 True。
这允许输入检查与 Agent 工作同时进行，是性能取舍，不是“执行前已批准”。
公司设备路径必须先满足合同与人工批准再派发；不能把并行 guardrail 当唯一授权。
即使 SDK 最终能够停止本地运行，也不能撤销之前已经发送的硬件请求。
证据：`guardrail.py:72-103`。

```100:103:src/agents/guardrail.py
    run_in_parallel: bool = True
    """Whether the guardrail runs concurrently with the agent (True, default) or before
    the agent starts (False).
    """
```

## 三：流式路径保存已完成结果并清理任务

`run_input_guardrails_with_queue()` 为规则创建 asyncio tasks，并按完成先后消费。
每个完成结果先追加到 `streamed_result.input_guardrail_results`，避免异常出口遗漏。
tripwire 触发时记录结果、向队列发送、取消其余任务并 gather 等待清理。
随后在已存在父 span 或当前 span 中记录错误，避免要求某一个固定 span 已建好。
异常分支也取消未完成任务并等待收尾，必要时终止 run loop、投递完成标记。
证据：`run_internal/guardrails.py:55-111`。

可借鉴点是“事实先入累积器再传播异常”和“取消要回收任务”，不是无限并发。
本项目已有执行状态，外部作业为 unknown 时仍必须对账，不能依赖 SDK cancel。

## 四：输出检查与执行期检查不同

`OutputGuardrail` 的文档明确针对 Agent 最终输出。
检查最终文本可以发现回复风险，但不能补救已经发生的工具副作用。
公司还需 provider 输出 schema、句柄归属、禁止科学正文和凭据回显检查。
这些现有规则在 `invoke.py` 与 `sanitize.py`，不应移到模型最终回答之后。
证据：`guardrail.py:133-139`。

## 测试证据

`tests/test_guardrails.py:49-58` 验证空 guardrail 集返回空结果。
`:61-84` 验证同步规则不触发/触发时布尔位和 output_info 透传。
`:87-108` 展示异步规则对应测试安排。
它们证明 SDK 封装和规则返回语义，不证明公司审批或第三方模型检测准确率。
测试导入 ScriptedModel 与运行内部函数，也说明无需真模型即可构造很多控制流反例。
本次未执行测试。

## 对公司代码的具体建议

1. `contracts/results.json` 继续限制诊断字段，记录规则 ID/状态若新增需先改合同。
2. `src/company_agent/invoke.py` 保留执行前策略，不用并行 guardrail 替代。
3. `packages/company-agent-core/src/runtime.js` 的取消/超时测试可对照任务清理场景。
4. `tests/test_bridge_behavior.py` 加强“错误出口已完成事实不丢失”的对照回归。
5. `tests/` 中模型判分作为效果层，不覆盖确定性的 deny/ask 红线。

## 冲突和未验证项

不引入 SDK Runner、handoff 链和其工具循环。
本篇没有审查该仓所有托管工具、远程 tracing 默认设置或所有模型适配器。
因此不宣称整个 SDK 可离线、无数据外发或达到公司部署要求。
每个候选子模块还需检查出网面、日志字段和许可证依赖。

## 结论

借鉴结构化规则结果和异步清理；保留公司设备授权的强顺序。
撤回“guardrail 机制天然等于合同权限门”的泛化理解。
这是一份静态实现复核，不是对 OpenAI 服务、模型或 SDK 全部功能的认证。

## 证据

- `LICENSE:1-21`。
- `src/agents/guardrail.py:19-45,72-103,111-130,133-139`。
- `src/agents/run_internal/guardrails.py:31-52,55-111,114-136`。
- `tests/test_guardrails.py:49-84,87-108`。
