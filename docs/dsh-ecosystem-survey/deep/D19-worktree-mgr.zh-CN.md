# D19 · worktree-mgr

验证级别：静态阅读。提交 `35d2ee736642b004c173c615cff1d6e9970f19dd`，提交时间 2026-10-05T07:13:36+08:00。没有运行上游测试，没有装入公司桌面。

目录卡片：D105。仓库：[JohnXu22786/worktree-mgr](https://github.com/JohnXu22786/worktree-mgr)。目录级判定是只借机制。

## 许可证

MIT。`LICENSE:1`。

## 调用链

文件头写明加载顺序：补丁插入插件行，`apply` 在 tools 服务就绪后把工具登记进 `ctx.tools`。实现就是构造 `GitRunner`，再逐个 `register`。

## 证据锚

1. `LICENSE:1`
2. `LICENSE:3`
3. `index.js:9-13`
4. `index.js:26-27`
5. `index.js:33-38`
6. `tests/tools.test.js:1`

## 引用

位置 `index.js:33-38`。

```
export function apply(ctx, config = {}) {
  const git = new GitRunner()
  const tools = createToolSet({ config, git })
  for (const tool of tools) {
    ctx.tools.register(tool)
  }
```

## 测试

快照含 `tests/tools.test.js`。本轮没有运行。

## 公司边界

一个任务一个工作树与公司「一工单、一次会话、一个工作树」同向。登记停留在现有会话的工具表，不另开仓库管家进程。
