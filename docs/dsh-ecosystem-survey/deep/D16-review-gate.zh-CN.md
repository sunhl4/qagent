# D16 · review-gate

验证级别：静态阅读。提交 `e979d7512c896c1c0e265882dc847c39bac95765`，提交时间 2026-09-30T04:46:34+08:00。没有运行上游测试，没有装入公司桌面。

目录卡片：D119。仓库：[JohnXu22786/review-gate](https://github.com/JohnXu22786/review-gate)。目录级判定是只借机制。

## 许可证

MIT。`LICENSE:1`。

## 调用链

`applyVote` 拒绝空评审者。回合为 0 时抛错，投票不能落在还没跑过审查的会话上。同一评审者在同一回合的投票会按索引覆盖。

## 证据锚

1. `LICENSE:1`
2. `LICENSE:3`
3. `src/approval/flow.ts:28-36`
4. `src/approval/flow.ts:38-40`
5. `cordis.patch.yml:1`
6. `test/approvalFlow.test.ts:1-4`

## 引用

位置 `src/approval/flow.ts:28-40`。

```
export function applyVote(session: ReviewSession, input: VoteInput): ReviewSession {
  if (input.reviewer.trim().length === 0) throw new Error('reviewer must not be empty')
  const vote: ReviewVote = {
    reviewer: input.reviewer,
    decision: input.decision,
    comment: input.comment?.trim().slice(0, 1000) || undefined,
    round: session.round,
    createdAt: input.now,
  }

  if (session.round === 0) {
    // No review has been run yet: votes would apply to nothing, reject loudly.
    throw new Error('cannot vote on a session that has not been reviewed yet (run a review first)')
```

## 测试

`test/approvalFlow.test.ts` 导入 `applyVote`。本轮没有运行。

## 公司边界

审查还没发生就不能投票，这条顺序可以参考。法定人数不代替设备批准，也不代替 `lab` / `sign` 的询问。
