# D09 · thoughtdag

验证级别：静态阅读。提交 `01df9605c13eb423d7bcbbb93d592d53164e6379`，提交时间 2026-11-08T13:54:29+01:00。没有运行上游测试，没有装入公司桌面。

目录卡片：D151。仓库：[chenxiachan/thoughtdag](https://github.com/chenxiachan/thoughtdag)。目录级判定是暂缓。

## 许可证

MIT。`LICENSE:1`。

## 调用链

补丁把 SPA 挂到同一 DSH 源的 `/thoughtdag/`。工具登记把画布动作转成 `ctx.tools`。`approval/request` 上，同一会话、同一工具、同一参数的既有规则会直接返回 `allowed-once`，并记 `auto: true`。

## 证据锚

1. `LICENSE:1`
2. `LICENSE:3`
3. `dsh/cordis.patch.yml:1-8`
4. `dsh/lib/index.js:972-976`
5. `dsh/lib/index.js:984-988`
6. `dsh/lib/index.js:1331-1336`

## 引用

位置 `dsh/lib/index.js:984-988`。

```
    // a standing allowance covers exactly this step: same tool, same arguments
    const rule = call ? `harness:${name}:${stepKey(call.arguments)}` : null
    if (rule && sessionRules.get(sessionId)?.has(rule)) {
      entry.emit({ approvalDecided: { id, outcome: 'allowed-session', auto: true, name, query, rule } })
      return 'allowed-once'
```

## 测试

快照含 `cli/test/dsh.test.mjs`。本轮没有运行。

## 公司边界

用连线选择送进模型的材料，这个界面可以参考，送入内容仍须是短摘录。自动把同一参数的批准记成允许，不能用于公司设备、云或超算。目录级暂缓维持。
