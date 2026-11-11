# D21 · sieve

验证级别：静态阅读。提交 `147915819213e5f97841db512c07181d3af839e6`，提交时间 2026-11-01T11:26:44+08:00。没有运行上游测试，没有装入公司桌面。

目录卡片：D150。仓库：[Sev7eEn7/sieve](https://github.com/Sev7eEn7/sieve)。目录级判定是只借机制。

## 许可证

MIT。`LICENSE:1`。

## 调用链

文件头写明没有裁判模型时插件不改变任何东西，并且禁止追加自己的会话事件类型，否则旧日志无法恢复。`agent/created` 只把代理记进内存表。裁判可以是独立的 Laya 或 System One 端点。

## 证据锚

1. `LICENSE:1`
2. `LICENSE:3`
3. `packages/dsh-sieve/src/index.ts:1-8`
4. `packages/dsh-sieve/src/index.ts:10-14`
5. `packages/dsh-sieve/src/index.ts:117`
6. `packages/dsh-sieve/cordis.patch.yml:1`

## 引用

位置 `packages/dsh-sieve/src/index.ts:10-14`。

```
 * sieve must not append its own Session event types: at the pinned DSH version
 * a stored log containing an unknown event without the `ignorable` envelope
 * marker refuses to resume, and `Session.append` cannot set that marker
 * (tests/contracts/plugin-event-restore.spec.ts). State is derived from native
 * events or kept in `ctx.storage`.
```

## 测试

快照含 `packages/dsh-sieve/src/judge/admission/test-log.ts`。本轮没有运行。

## 公司边界

工具输出先裁短再进模型，这条和短结果同向。独立裁判模型和额外事件类型不接入公司会话。
