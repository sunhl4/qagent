# H20 MCP Inspector：认证诊断不应掩盖发行方错配

项目 `modelcontextprotocol/inspector`；SHA `0cac110a809e93753fa353810b9b4c91e89810fc`，提交2026-10-21T14:10:36-04:00；来源 `/tmp/oss-modelcontextprotocol-inspector`。静态阅读，未登录MCP服务；许可根LICENSE。

## 链路与机制

Inspector连接协议客户端时，OAuth callback可因discovery state丢失或发行方改变抛同一个SDK错误。`core/auth/issuerBinding.ts` 把两者细分为lost_authorization_state和issuer_mismatch，再供UI决定重新授权还是显示安全错误。

- `isAuthorizationServerMismatchShape`同时核字段类型和SDK isInstance；序列化边界保留name时有fallback，避免跨bundle class身份失效。
- 缺失state用sentinel或非HTTP URL识别。该分类依赖SDK错误形状，不是一般认证标准，升版必须回归。
- 沿cause/data.cause递归寻找内部错误，用seen防循环；不能为了“用户体验”把真正issuer错配修成重新登录重试。

```33:34:core/auth/issuerBinding.ts
/** Phrase the SDK puts in the `recordedIssuer` slot when nothing was recorded. */
const MISSING_DISCOVERY_STATE_PHRASE = "discoveryState was not available";
```

## 测试

`clients/web/src/test/core/auth/issuerBinding.test.ts:27-43`用真实SDK错误验证brand在类上不在实例上；`:65-107`检查缺失state和真实issuer错配；`:109-159`检查包装链与循环终止。
测试用真实错误类型而非伪fixture很重要，否则可能测试通过但线上识别失败。未运行测试。

## 对公司

Inspector适合开发期工具发现/认证诊断，不作为公开生产管理端。后台账号有效、会话状态丢失、权限不足、发行方错配应分别显示，不能统一说平台离线。
`providers.py`与工作台状态映射保持安全分类；SDK异常不得包含凭据回模型。测试包括跨bundle错误、恢复丢state与issuer变化，且设备批准不因重连复用。

证据：issuerBinding.ts:1-28,33-51,71-107,115-130；issuerBinding.test.ts:27-159；LICENSE。未审全部Inspector CLI/proxy安全，仅此认证诊断链。
