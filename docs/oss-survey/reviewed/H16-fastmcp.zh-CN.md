# H16 FastMCP：授权中间件与结果限制复核

- 仓库：`jlowin/fastmcp`。
- SHA：`e95877e76422661709f88b4066023dc5569b1a68`，提交 2026-10-21T16:37:11-05:00。
- 来源：`/tmp/oss-jlowin-fastmcp`。
- 验证：静态实现与测试阅读，未启动 MCP 或调用云服务。

## 关键结论

FastMCP 可作为 Python MCP server 框架候选，避免自写协议层。
但旧稿“AuthMiddleware + ResponseLimitingMiddleware 已足够治理”不成立：STDIO OAuth 行为与结果截断方式都不同于公司合同。

## 实际机制链

`AuthMiddleware` 接入工具/资源/prompt 发现与执行；它组合 callable auth checks。
资源列表按授权过滤，执行前再校验，优于仅隐藏列表。
其 `_requested_version()` 从 request meta 中解析版本条件；不合法 meta 返回 None，而不是公司式坏信封统一拒绝。
`ResponseLimitingMiddleware` 拦截工具结果，按工具选择与字节限额截成 TextContent。
证据：`fastmcp_slim/fastmcp/server/middleware/authorization.py:55-115`；`response_limiting.py:22-99`。

## 授权边界

AuthMiddleware 明确说明 STDIO transport 没有 OAuth 概念，跳过这类检查。
这不等于 STDIO 应当公开无权限：宿主可能用进程启动和文件权限建立信任，但公司仍必须在 invoke 前执行合同策略。
因此不能假设同一个 middleware 在所有传输都提供同样授权保证。

```89:94:fastmcp_slim/fastmcp/server/middleware/authorization.py
    The middleware:
    - Filters tools/resources/prompts from list responses based on auth checks
    - Checks auth before tool execution, resource read, and prompt render
    - Skips all auth checks for STDIO transport (no OAuth concept)

    Args:
```

多个 scope 检查的错误提示会汇总能安全披露的 scope shortfall；不会越过不透明检查暴露后续需求。
这是授权解释信息的最小披露参考，不是公司可以自动升级 scope 的依据。
证据：`authorization.py:117-139`。

## 结果限制不等于科学结果完整性

默认 max_size 为 1,000,000 字节，tools=None 覆盖所有工具，空列表实际不限制任何工具。
过限逻辑提取文本、按 UTF-8 边界截断、追加后缀并返回 TextContent。
工具错误标志可以保留，但输出形状可能不再是原来的结构化内容。
公司结果上限是64,000字节且拒绝有损科学结果，不能直接采用这一转换作为最终结果合同。

## 测试证据

`tests/server/middleware/test_response_limiting.py:25-50` 验证小结果原样通过，大文本被截并有标记。
`:52-64` 验证截断错误结果仍为 error。
`:66-95` 验证按工具名选择：受限工具无 output_schema，未受限工具保留 output_schema。
这特别说明“有限响应”与“强输出 schema”可能存在取舍；公司不能因为中间件截断就忽略 schema 失配。
本轮未运行这些测试。

## 公司映射

1. MCP 新服务可用框架，但身份/租户/设备审批仍由公司 `contracts/` 与 Python adapter 执行。
2. STDIO、Streamable HTTP 两种传输都加入准入用例，不能只测其中之一。
3. `sanitize.py` 继续拒绝超限或敏感科学结果，不把 JSON 降为裁剪文本后标成功。
4. 合同测试覆盖 tools=[]、Unicode 字节边界、结构化结果丢失、错误结果泄密。
5. 只读标签和列表可见性是辅助信息，不能给予 `quantum_device_run` 免审权限。

## 许可与范围

根 `LICENSE:1-13` 为 Apache-2.0；具体依赖和所用版本仍需同步审查，不作法律合规保证。本篇聚焦上述两个中间件，未审框架全部 OAuth/OIDC provider、存储和远程功能。

## 取舍

协议框架候选可保留；“全部治理足够”的结论撤回。
公司硬规则高于任何通用中间件默认值，且禁止为省事另起生产工具循环。
