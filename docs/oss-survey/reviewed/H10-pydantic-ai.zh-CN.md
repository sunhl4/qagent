# H10 Pydantic AI：延期工具与批准关联

项目 `pydantic/pydantic-ai`；SHA `eb0bd084f7cfa08043d27218947846a7fb293823`，提交2026-10-21T21:56:20-05:00；来源 `/tmp/oss-pydantic-pydantic-ai`。根LICENSE MIT。静态源码/测试，未运行框架。

## 实际协议链

`DeferredToolRequests` 分calls和approvals，分别代表外部执行和人工确认；build_results校验返回key属于对应pending集合，再产生DeferredToolResults；remaining按已解决call ID过滤剩余请求，全部完成返回None。

## 三个细节

1. 错误关联ID直接ValueError，审批和执行结果不能随意放错集合，值得用于公司恢复信封测试。
2. approve_all=True会给所有未指定批准项填ToolApproved；这是便利API，不符合公司设备逐次ask边界，不能暴露给模型。
3. ToolApproved允许override_args，旧稿只写approve/deny漏掉关键风险。参数改变后需要重新核对批准范围，而非把批准看作任何参数都有效。

```41:45:pydantic_ai_slim/pydantic_ai/_deferred.py
    """Tool calls that require external execution."""
    approvals: list[ToolCallPart] = field(default_factory=list[ToolCallPart])
    """Tool calls that require human-in-the-loop approval."""
    metadata: dict[str, dict[str, Any]] = field(default_factory=dict[str, dict[str, Any]])
    """Metadata for deferred tool calls, keyed by `tool_call_id`."""
```

## 注册测试

`tests/test_tools.py:70-102`检查需要context的工具首参必须RunContext，plain工具不能偷带RunContext；`:105-122`检查无法推导签名的builtin注册报错。可借注册期校验，不必导入完整Agent graph。
本轮没有运行延期恢复与模型交互测试，不把类型存在当端到端保证。

## 公司落点

- `contracts/`先定义批准关联所需字段；不直接照搬approve_all。
- `policy.py`与插件保持mandatory ask，参数变更产生新批准请求。
- `tests/test_plugin_runtime.py`覆盖错误call ID、跨用户结果、重复恢复及部分完成。
- 资源句柄仍三类；tool_call_id是关联元数据而非新科学资产句柄。

证据：_deferred.py:29-45,47-89,91-110；tests/test_tools.py:70-122；LICENSE。只借协议形状，不引第二循环。
