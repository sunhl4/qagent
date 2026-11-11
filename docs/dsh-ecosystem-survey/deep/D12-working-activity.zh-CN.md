# D12 · working-activity

验证级别：静态阅读。提交 `8999ac3312df3a8d9e0b09ce81eb26d16ccab695`，提交时间 2026-10-19T03:14:19+08:00。没有运行上游测试，没有装入公司桌面。

目录卡片：D072。仓库：[ccch1mneyyy/working-activity](https://github.com/ccch1mneyyy/working-activity)。目录级判定是思想可取。

## 许可证

MIT。`LICENSE:1`。

## 调用链

`apply` 先登记活动事件类型，再按配置渲染状态行。`publish` 默认 false。会话事件更新追踪器后，把实时覆盖层重新绑到新的状态对象，避免读到过期的一行。

## 证据锚

1. `LICENSE:1`
2. `LICENSE:3`
3. `packages/activity/working-activity/src/index.ts:162-168`
4. `packages/activity/working-activity/src/index.ts:169-172`
5. `packages/activity/working-activity/src/index.ts:485-493`
6. `packages/activity/working-activity/tests/hud.spec.ts:1`

## 引用

位置 `packages/activity/working-activity/src/index.ts:162-172`。

```
export function apply(ctx: Context, config: Config = {}): void {
  // Register the event type BEFORE anything can publish or validate: the
  // strict read paths (resume seed validation, persistence load) refuse
  // logs with unknown non-ignorable types. Registration is unconditional —
  // it also protects READING logs written by an earlier publish:true era
  // in processes where publishing itself is off. See registration.ts.
  registerActivityEventType()
  const resolved: ResolvedConfig = {
    // `mode: minimal` renders functional labels only (pi extension parity).
    phrases: config.phrases ?? config.mode !== 'minimal',
    publish: config.publish ?? false,
```

## 测试

快照含 `packages/activity/working-activity/tests/hud.spec.ts`。本轮没有运行。

## 公司边界

会话页上的短状态行适合上游界面。默认不把活动流写进会话日志，和公司短回执同向。
