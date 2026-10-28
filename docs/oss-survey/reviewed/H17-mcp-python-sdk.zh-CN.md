# H17 MCP Python SDK：协议错误与工具错误分离

项目 `modelcontextprotocol/python-sdk`；SHA `2af9e3089ac66b35c1550c500aae86a82efb1e17`，提交2026-10-17T15:54:35+02:00；来源 `/tmp/oss-modelcontextprotocol-python-sdk`。静态复核，未运行MCP server或上游测试。

## 当前实现链

本快照low-level Server使用构造器on_list_tools/on_call_tool等handler，不应继续引用旧fastmcp路径。
HandlerEntry同时存params_type和handler，ServerRunner按method找到入口、验证params、构造context并调用。
HTTP路径接入AuthContext、BearerAuth、transport security、session manager；STDIO是另一种运输，不能将HTTP认证默认推断到STDIO。
证据：`src/mcp/server/lowlevel/server.py:1-34,48-78,86-106`。

## 关键机制

- 参数模型和handler关联在注册期建立，而不是运行时仅按函数名反射；公司合同到注册的投影也要一一对应。
- `CallToolResult.is_error`代表业务工具失败，可作为结果返回给模型；协议层失败才是JSON-RPC错误。公司必须再映射为自身ok/error/needs_ask，不能只看HTTP成功。
- 能力与传输安全配置是框架入口，不自动解决租户/设备权限；model-visible annotations不是授权来源。

```93:96:src/mcp/server/lowlevel/server.py
class HandlerEntry(Generic[LifespanResultT]):
    """A registered handler and the params model to validate incoming params against.

    Stored in `Server._request_handlers` / `_notification_handlers` and consumed
```

## 测试证据

`tests/interaction/lowlevel/test_tools.py:32-53`通过公共Client调用Server，断言args到handler以及文本结果5回客户端。
`:56-65`开始明确工具is_error结果与协议异常区别。此为可重复协议交互用例，不需QPU；本轮只阅读未执行。

## 公司落点

- `providers.py`和`invoke.py`继续校验工具结果schema/状态/句柄，不让MCP result透传破坏合同。
- 新MCP adapter测试列表发现、未知工具、参数错型、is_error、取消和短结果。
- 对内部账号服务，MCP认证成功仍需业务权限与租户资源检查。
- 不将Python SDK的测试服务循环当第二生产Agent循环；SDK本身协议库可候选复用。

证据：lowlevel/server.py:1-34,48-78,86-106,109-120；interaction/lowlevel/test_tools.py:32-65；LICENSE。版本/许可需按固定源核验，不沿用历史标签推断当前包布局。
