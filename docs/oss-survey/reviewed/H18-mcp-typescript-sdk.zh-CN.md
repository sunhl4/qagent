# H18 MCP TypeScript SDK：输入/输出验证复核

- 仓库：`modelcontextprotocol/typescript-sdk`。
- 固定 SHA：`c05225a636c679870b65f8ca4fe83a76ea1cf113`。
- 提交：2026-10-21T01:09:57+03:00。
- 来源：`/tmp/oss-modelcontextprotocol-typescript-sdk`。
- 根 package 标 `2.0.0-alpha.0`；这是本快照声明，不推断所有已发布包版本相同。
- 验证：静态源码/测试；未执行 SDK conformance。

## 纠错与模块结构

原稿声称 `src/` 目录并列泛泛协议常量，实际本快照核心在 `packages/server`、`packages/client` 和 `packages/core-internal`。
服务端 `McpServer` 负责注册及执行前后验证；客户端也有缓存驱动的输出验证，但不能假定永远发生。

## 实际调用链与边界

工具注册保留 inputSchema/outputSchema 与 executor。
收到调用后，server 校验输入元素数量和 Standard Schema，再进入 executor。
执行完成后验证输出；input-required 中间结果与 isError 结果有特定例外。
最后把符合协议的结果交给传输层返回。
证据：`packages/server/src/server/mcp.ts:345-427`。

### 输入限制先于业务函数

`validateToolInput()` 在配置 `_maxToolInputElements` 时计算元素总数，过限抛 InvalidParams。
没有 inputSchema 时返回 undefined，而不是自动验证任意输入。
有 schema 时以 args ?? {} 验证，失败将错误变成协议错误，成功返回 schema 转换后的数据。
因此“用 SDK”不代表公司所有工具都有完整闭合 schema；公司必须注册自己的严格合同。

### 输出是“存在性检查”，不是简单 truthy 检查

代码只把 structuredContent===undefined 看作缺失。
合法 null/0/false/空字符串是否可用由输出 schema 决定，而不是被布尔判断误丢。
这对公司允许零计数/概率的科学摘要很重要。

```403:408:packages/server/src/server/mcp.ts
        if (result.structuredContent === undefined) {
            throw new ProtocolError(
                ProtocolErrorCode.InvalidParams,
                `Output validation error: Tool ${toolName} has an output schema but no structured content was provided`
            );
        }
```

### 中间态与错误态不冒充成功输出

input-required 不是最终结果，因此跳过最终 outputSchema；isError 也直接返回。
公司要在自己的状态合同里明确 needs_ask/denied/error/ok，不因为协议允许错误结果就接收任意正文。
工具失败内容同样不得含密钥、完整电路或敏感诊断。

## 测试证据

`test/integration/test/server/mcp.test.ts:14-70` 建立 in-memory client/server，检查 logging 能力和 notification 收到的结构。
`:75-109` 注册工具，通过 ctx.mcpReq.log 产生日志并由 client.callTool 调用。
这证明能用内存传输测试完整工具通信，不证明真实 HTTP/OAuth、多租户和公司审批已通过。
建议公司开发期使用这一形态写 MCP adapter 合同测试，生产仍由 DSH 调度。

## 客户端不能当最终保障

`packages/client/src/client/client.ts:2391-2400` 说明 callTool 自己不发 tools/list；冷缓存可跳过输出 schema 验证。
这属于兼容性行为。因此公司 `invoke.py` 仍必须独立校验返回信封和输出 schema，不依赖客户端“应该已经验证”。

## 许可

根 LICENSE 声明从 MIT 向 Apache-2.0 过渡，新代码与规范用 Apache-2.0、非规范文档 CC-BY-4.0。旧部分及具体包需按所用版本的声明审查；不能把所有历史代码统一重标。

## 公司落点

1. `contracts/tools.json` 每项输入/输出显式闭合，缺失 schema 注册失败。
2. `runtime.js` 中 dshSchema 投影与 Python 完整验证继续双侧校验。
3. MCP client 缓存冷/热两种状态都测试未知字段、错误类型和零值输出。
4. input-required 只作为协议状态，不替代公司 ask 的人工授权来源。
5. 锁定 SDK 与协议版本，升版跑内存/真实传输两层测试后才引入生产。

## 证据

- `package.json:1-18`、`LICENSE:1-3`。
- `packages/server/src/server/mcp.ts:345-379,381-418,420-429`。
- `packages/client/src/client/client.ts:2391-2400`。
- `test/integration/test/server/mcp.test.ts:14-70,75-109`。

本篇不审全部协议扩展和认证实现；“静态复核通过”不代表 SDK 当前 alpha 可直接生产使用。
