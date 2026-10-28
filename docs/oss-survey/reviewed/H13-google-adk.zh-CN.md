# H13 Google ADK：函数工具、校验与确认复核

- 项目：`google/adk-python`。
- SHA：`d324744645ee372db8ecce4c0209e9c70ce18e0b`。
- 提交：2026-10-21T17:50:59-07:00。
- 来源：`/tmp/oss-google-adk-python`。
- 许可：本次阅读源码文件头 `src/google/adk/tools/function_tool.py:1-13` 为 Apache-2.0。
- 验证：静态阅读实现及测试，未连接 Gemini、公司模型或设备。

## 定位

ADK 是完整 Agent 框架，不能作为第二生产 runtime 装入公司系统。
本篇研究 FunctionTool 的 schema、参数与确认边界。
它说明“类型化工具”需要精读具体行为，不能只因使用 Pydantic 就说严格失败闭合。

## 调用链

`FunctionTool.__init__()` 通过 CallableSpec 读取函数、名称、文档和上下文参数。
`_get_declaration()` 生成函数声明并隐藏 context/input_stream 参数。
`run_async()` 先预处理并校验入参，再准备真实函数调用参数。
`check_require_confirmation()` 可以调用静态布尔位或函数来决定是否需要确认。
`BaseTool` 另声明 long-running 与 deferred response 语义，但不因此保证外部事务。
证据：`function_tool.py:160-246,264-310,371-424,469-480`；`base_tool.py:57-89`。

## 一：schema 缓存要包括影响声明的开关

`_build_declaration_cached()` 用函数、被忽略参数、API variant 和 JSON schema 特性位组成缓存键。
其中 feature flag 即使不参与函数体处理，也通过缓存键隔离结果。
`_get_declaration()` 对可哈希和不可哈希函数分别走全局/实例缓存。
返回声明采用 deep copy，避免调用方加前缀时污染共享缓存。
证据：`function_tool.py:55-76,214-246`。

公司插件从合同投影 schema，也要防止缓存跨合同版本泄漏。
这应在现有 `contract_snapshot` 与 `dshSchema` 测试上扩充，而不是换一套工具真源。

## 二：确认默认关闭，不符合设备缺省

构造函数的 `require_confirmation` 默认 False，可以接收函数。
参数级确认有用，但公司设备工具的 mandatory ask 不得交给动态风险分类器。
模型或 callable 决定“无需确认”不能覆盖 `lab/sign=ask`。
证据：`function_tool.py:167-190,405-424`。

```167:172:src/google/adk/tools/function_tool.py
  def __init__(
      self,
      func: Callable[..., Any],
      *,
      require_confirmation: Union[bool, Callable[..., bool]] = False,
  ):
```

## 三：类型校验存在 feature flag 与跳过路径

`_preprocess_args_with_validation()` 仅在 FUNCTION_TOOL_ARG_VALIDATION 开启时做额外校验。
没有函数签名时，直接返回预处理参数且不带校验错误。
`_validate_args()` 使用 TypeAdapter 转换原始值，对未支持注解可能记录 warning 后跳过。
因此不能把该接口直接当公司闭合 JSON schema 边界。
证据：`function_tool.py:264-355`。

这不是判定 ADK 存在漏洞，而是两种产品的容错目标不同。
公司未知字段/错误类型要拒绝，不应因为上游容错而默默执行。

## 四：未知参数过滤与异常分类要分别理解

`_prepare_invocation_args()` 注入 ToolContext 和当前调用的 input_stream。
它最终只保留签名中存在的参数，意味着额外字段可能被过滤而非拒绝。
`_is_invocation_type_error()` 检查 traceback 是否经过目标函数体，区分绑定错误与内部缺陷。
后者设计可用于避免把真实实现 bug 提示成“用户改参数即可”。
证据：`function_tool.py:371-403,426-466`。

公司不能复制参数过滤行为到严格信封，但可以借鉴错误类别区分。
内部错误仍返回短的安全摘要，不能把 traceback、源代码或凭据给模型。

## 长任务边界

`BaseTool.is_long_running` 声明先返回资源后续完成。
`_defers_response` 说明空返回可能跳过自动 FunctionResponse，由外部补回。
这能帮助设计受理/完成分离，但资源 ID 不自动成为公司允许的句柄。
HPC/QPU 的运行事实、取消状态和费用仍需平台查询。

## 测试证据

`tests/unittests/tools/test_function_tool.py:132-137` 检查名称、description 和 func 引用。
同文件通过 mock ToolContext 和同步/异步测试函数验证调用包装基础。
这些测试存在不等于公司权限或真实端点兼容通过。
本轮未运行。

## 公司落点

1. `contracts/tools.json` 保持 additionalProperties=false，不以签名过滤替代拒绝。
2. `packages/company-agent-core/src/runtime.js` 的 schema 缓存绑定合同快照与版本。
3. `src/company_agent/policy.py` 保持 mandatory ask，不让参数 callable 覆盖。
4. `tests/test_schema.py` 覆盖未知字段、未支持类型、schema 投影失配。
5. 长作业测试区分 accepted、running、completed、unknown，不直接照搬 ADK 资源名。

## 证据与范围

- `src/google/adk/tools/function_tool.py:1-13,55-76,167-190,214-246,264-355,371-424,426-480`。
- `src/google/adk/tools/base_tool.py:57-89`。
- `tests/unittests/tools/test_function_tool.py:132-137`。
- 未审完整 ADK 模型、内置 Google 工具、远程托管和全部 session store；不做全框架安全保证。
