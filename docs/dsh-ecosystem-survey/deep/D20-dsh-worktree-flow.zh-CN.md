# D20 · dsh-worktree-flow

验证级别：静态阅读。提交 `046756d8712ddfefccfdc5e504854d4745bc41a7`，提交时间 2026-09-01T17:17:57+08:00。没有运行上游测试，没有装入公司桌面。

目录卡片：D095。仓库：[TY-ang/dsh-worktree-flow](https://github.com/TY-ang/dsh-worktree-flow)。目录级判定是只借机制。

## 许可证

MIT。`LICENSE:1`。

## 调用链

补丁在基础组合之后插入一行，并声明由宿主读取 `dsh.bundle.patch`。`assertSafeMutationRuntime` 在第一次副作用之前调用 Windows 进程检查，失败即闭合。特性名经 `slugifyFeature` 收成目录名。

## 证据锚

1. `LICENSE:1`
2. `LICENSE:3`
3. `cordis.patch.yml:1-10`
4. `lib/core.js:61-68`
5. `lib/safety.js:12-14`
6. `test/core.test.mjs:1`

## 引用

位置 `lib/safety.js:12-14`。

```
/** Fail closed on Windows before a caller performs its first side effect. */
export async function assertSafeMutationRuntime(ctx, signal) {
	return assertNormalWindowsProcess(ctx, signal);
```

## 测试

快照含 `test/core.test.mjs`。本轮没有运行。

## 公司边界

多仓同一功能分支的目录映射可以作思想。安全检查留在现有会话的工具里，不另写仓库管理器。
