# H01 OpenCode：权限求值与请求生命周期

来源 `sst/opencode`；SHA `1b1ad488f833e37af57d903d995a3bdbef752756`，提交2026-10-21T20:21:47-05:00。克隆 `/tmp/oss-sst-opencode`。静态源码及测试阅读，未运行 Bun 测试或模型。许可证以根 LICENSE 为准。

## 调用链

`packages/core/src/permission.ts` 的 Service 暴露 ask/assert/reply/get/list。工具请求包含 session、action、resources 与可选 agent；服务依赖 Agent、SessionStore、PermissionSaved、Bus 和 PluginHooks。需要询问的请求在内存 pending map 中保存 Deferred，reply 完成或拒绝该等待。

## 三个实现机制

1. `evaluate()` 展平多个规则集后使用 findLast，因此后匹配规则优先；没有匹配时默认 ask。缺失 agent 的备用规则却是全 deny。两种“缺省”不能混说。
2. 权限错误分 BlockedError、CorrectedError、DeclinedError，改正反馈和策略拒绝不是相同状态；工具层不得把它们改写为成功。
3. `close` 遍历 pending，发布 reject 事件，并用 ensuring 保证 Deferred 失败完成，避免会话关闭后审批永远悬挂。

```19:19:packages/core/src/permission.ts
const missingAgentPermissions: Permission.Ruleset = [{ action: "*", resource: "*", effect: "deny" }]
```

## 测试的实际范围

`packages/core/test/permission.test.ts:100-113` 验证 allow/deny 不入审批队列，无匹配 ask 入队。
`:139-148` 验证 assert 对 deny 产生 BlockedError；`:151-157` 验证 Windows 路径规则与 slash-normalized 资源匹配。
`:160-172` 区分受管产物读取与外部目录读取权限。这些是有具体断言的策略测试，不证明公司跨端审批已集成。

## 对公司的结论

可借请求等待清理、拒绝错误分类和派生规则测试；不引入 OpenCode Runtime。
公司未知工具/未知preset必须 deny，不能照搬“未命中 ask”。参数改动后要重新确认，设备不能使用永久允许记忆。
`policy.py` 已有合同校验，后续在插件生命周期测试中补关闭会话、并行审批、跨会话回复、过期批准等反例。
`runtime.js` 继续以合同工具映射为边界；路径可读性与作业提交授权分离。

## 证据与未验证项

实现 `permission.ts:19-31,51-88,100-130`；测试 `permission.test.ts:100-172`；根 LICENSE。
本文未全面核查规则持久化、全部插件和模型适配。原稿仅凭默认值给出星级“对齐度”的结论撤回。
