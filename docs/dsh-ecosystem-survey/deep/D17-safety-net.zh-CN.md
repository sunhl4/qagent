# D17 · safety-net

验证级别：静态阅读。提交 `a6686f16514304b930d4384a603bf2ac5ca67390`，提交时间 2026-10-24T12:20:25+08:00。没有运行上游测试，没有装入公司桌面。

目录卡片：D120。仓库：[JohnXu22786/safety-net](https://github.com/JohnXu22786/safety-net)。目录级判定是只借机制。

## 许可证

MIT。`LICENSE:1`。

## 调用链

文件头约定放行必须 `return next()`，抛异常不是拒绝途径。`combineMatches` 里致命规则不能降成放行。`apply` 在 ask 模式下如果没有 approval 服务，把询问改成 deny。判定过程自己抛错时也 deny。

## 证据锚

1. `LICENSE:1`
2. `LICENSE:3`
3. `plugin.js:11-14`
4. `plugin.js:270-278`
5. `plugin.js:283-288`
6. `src/verdict.js:86-99`

## 引用

位置 `src/verdict.js:86-88`。

```
    if (m.severity === 'critical' && action !== 'deny') {
      warns.push(`规则 ${m.ruleId} 为致命规则，无法降级为放行，仍按拒绝处理`)
      action = 'deny'
```

## 测试

快照含 `test/verdict.test.js`。本轮没有运行。

## 公司边界

这是深读里最接近公司失败闭合的一道门：致命不可降级，没有批准通道就拒绝，判定失败也拒绝。公司仍用现有策略插件和授权卡，不并行安装这套规则库。
