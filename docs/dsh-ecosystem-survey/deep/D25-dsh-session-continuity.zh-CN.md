# D25 · dsh-session-continuity

验证级别：静态阅读。提交 `f22b8f98693d9d252a863025625f1ef3cbcfa318`，提交时间 2026-10-16T17:39:27+08:00。没有运行上游测试，没有装入公司桌面。

目录卡片：D139。仓库：[ymck-x/dsh-session-continuity](https://github.com/ymck-x/dsh-session-continuity)。目录级判定是只借机制。

## 许可证

MIT。`LICENSE:1`。

## 调用链

`agent/pre-step` 里，下游若已拒绝或已取消，原样返回。只在本会话第一个回合的第一个模型步骤注入一次。指针文本来自上一会话的标题和交接文件，注入失败只记警告并返回原决定。

## 证据锚

1. `LICENSE:1`
2. `LICENSE:3`
3. `index.js:97-98`
4. `index.js:115-120`
5. `index.js:131-137`
6. `test/run.mjs:1`

## 引用

位置 `index.js:115-120`。

```
  ctx.on('agent/pre-step', async ({ agent, turn, step, signal }, next) => {
    const decision = await next()
    // 不拥有这个决定：下游拒绝或已取消时原样返回。
    if (decision.kind === 'reject' || signal?.aborted === true) return decision
    // 只在本会话的第一个模型步骤注入一次；重试不会重跑 pre-step。
    if (turn !== 1 || step !== 1) return decision
```

## 测试

快照含 `test/run.mjs`。本轮没有运行。

## 公司边界

一行短指针与公司短回执同向。它不读取科学正文。自动交接文件若含全文，仍须在注入前裁短。
