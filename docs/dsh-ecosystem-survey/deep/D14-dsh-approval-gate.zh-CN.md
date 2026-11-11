# D14 · dsh-approval-gate

验证级别：静态阅读。提交 `4544496fb6f1408dc2f63da05979f28011ee5fb7`，提交时间 2026-10-22T22:56:13+03:00。没有运行上游测试，没有装入公司桌面。

目录卡片：D108。仓库：[GooDAnDReaDY/dsh-approval-gate](https://github.com/GooDAnDReaDY/dsh-approval-gate)。目录级判定是只借机制。

## 许可证

MIT。`LICENSE:1`。

## 调用链

`tools/pre-execute` 调用 `engine.decide`。检查抛错时返回 ask。无人值守且这次 ask 未锁定时，监听器 `return next()`，调用继续。`uncertainPolicy === "allow"` 时，guard 路径会自动放行 ask。宿主有 `ctx.tools.guard` 时再挂同步 guard。

## 证据锚

1. `LICENSE:1`
2. `LICENSE:3`
3. `lib/index.js:437-448`
4. `lib/index.js:490-492`
5. `lib/index.js:538-541`
6. `lib/index.js:558-559`

## 引用

位置 `lib/index.js:490-492`。

```
        if (forcedUnattended || isUnattended({ policy: knobs.policy, preset: knobs.preset, sandbox: knobs.sandbox, unattendedPolicies })) {
          return next();
        }
```

## 测试

扫描没有找到测试文件。放行分支没有在这个快照里被测试钉住。

## 公司边界

执行前拦截与公司策略插件同向。无人值守放行和不确定即允许不能进入公司。`lab` / `sign` 仍询问，`boot` / `algo` 仍拒绝。
