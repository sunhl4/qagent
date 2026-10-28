# H14 Mastra：工具校验与错误形态复核

- 项目：`mastra-ai/mastra`。
- SHA：`6a4a607e710000e46790e20f28c2355af9ca2a05`，提交2026-10-21T23:38:19-04:00。
- 来源：`/tmp/oss-mastra-ai-mastra`。
- 许可：`LICENSE.md:1-16`，任意 ee/ 目录用独立许可，其余主体 Apache-2.0；不能只标一个许可。
- 验证：静态源码与测试，未运行 TS 工程或模型。

## 调用链

工具构造保存 input/output/request-context schema；运行前通过验证辅助函数处理数据，执行器接收工具参数和 ToolExecutionContext，完成后检查输出。
本篇聚焦 `packages/core/src/tools/validation.ts` 和 `tool.ts` 的 request context 包装，未对完整 Agent/workflow 引擎作认证。

## 实现细节

**输入 schema 调用可能抛错。** safeValidate 捕获 Standard Schema 内部错误，明确拒绝异步 schema；返回结果同时有 value 和 issues 时优先 issues。这避免某些库校验失败却同时返回部分值导致误判。

**声明输出与运行时验证 schema 分离。** registerToolOutputValidationSchema 用 Symbol 缓存验证 schema；resolveToolOutputValidationSchema 优先取有效输出声明再回退缓存。公司应关注 schema 变更后缓存是否和合同版本一致，而不是复制两套真源。

**错误路径格式化。** createStandardSchemaIssuesError 将 path 分段提取，生成 per-field errors；调用方可准确告诉用户哪个字段错。公司依然需要脱敏错误值，不能打印参数全文。

**日志截断不是脱敏。** truncateForLogging 将数据 JSON.stringify 后限长200字符。长度短仍可能包含完整短密钥，因此不能作为公司凭据过滤替代。
证据：`validation.ts:7-31,42-68,105-118,165-180`。

```47:54:packages/core/src/tools/validation.ts
    const result = schema['~standard'].validate(data);
    if (result instanceof Promise) {
      throw new Error('Your schema is async, which is not supported. Please use a sync schema.');
    }
    // Prioritise issues over value: Valibot returns both on failure (typed: false).
    if ('issues' in result && Array.isArray(result.issues) && result.issues.length > 0) {
      return { issues: result.issues as readonly StandardSchemaIssue[] };
    }
```

## Request context

`tool.ts:32-44` 在验证器异常时返回 false；`:48-72` 的 encoder 仅支持可识别且可编码的 Zod schema，否则返回 undefined。
`TransformedRequestContext` 保存源 context 与变换结果，试图让显式修改与原共享状态连接。
这属于类型变换机制，不是用户身份可信证明；公司 user/tenant/provider 必须由服务端可信上下文绑定。

## 测试证据

`tool.test.ts:19-77` 构造 createTool，用 mockFindUser 检查参数传入、结果返回及不存在用户。
它证明工具包装按期调用，不证明整个框架 fail-closed。后续若借鉴输出验证，应选对应 schema 失败测试再运行。
本轮未执行测试。

## 公司落点

- `contracts/tools.json` 与 `schema.py` 保持明确错误字段路径；安全摘要不回显原输入。
- `runtime.js` schema 投影缓存不得与合同 digest 脱节。
- `sanitize.py` 继续匹配已知凭据与禁止正文，不用200字符截断当脱敏。
- `tests/test_schema.py` 覆盖 result 同时带 value/issues、异步 schema 不支持、输出缓存不一致。

## 取舍

只借工具 schema 和错误分类机制。Mastra Agent/workflow/记忆运行时不进入生产，DSH 仍唯一；ee 模块引入前单独查许可。

## 证据

`LICENSE.md:1-32`；`packages/core/src/tools/validation.ts:7-31,42-68,105-118,165-180`；`packages/core/src/tools/tool.ts:32-100`；`packages/core/src/tools/tool.test.ts:19-77`。
