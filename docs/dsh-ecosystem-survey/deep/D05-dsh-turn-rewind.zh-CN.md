# D05 · dsh-turn-rewind

验证级别：静态阅读。提交 `fa4fde65da2f503c0269d5425904bf9d9f340b34`，提交时间 2026-11-07T02:17:40+08:00。没有运行上游测试，没有装入公司桌面。

目录卡片：D053。仓库：[Anionex/dsh-turn-rewind](https://github.com/Anionex/dsh-turn-rewind)。目录级判定是思想可取。

## 许可证

BSD 3-Clause。`LICENSE:1`。

## 调用链

文件头把产品定义成带批准门的变更账本。服务构造时 `ctx.provide('changeLedger')`，再在 agents 与 web 服务上安装回退 HTTP。注释写明档案会把旧插件留在内存里，直到 DSH 重启。

## 证据锚

1. `LICENSE:1`
2. `LICENSE:3`
3. `src/index.ts:1-3`
4. `src/index.ts:18-23`
5. `src/index.ts:58-68`
6. `tests/engine.test.mjs:1`

## 引用

位置 `src/index.ts:58-65`。

```
  /** Register the service and startup reconciliation. */
  constructor(ctx: Context, config: ChangeLedgerConfig = {}) {
    const normalized = unwrapVolatileConfig(config)
    ctx.provide('changeLedger', this)
    this.engine = new ChangeLedgerEngine(normalized)
    const checkpoints = new TurnCheckpointCoordinator(this.engine)
    ctx.logger.info(`[turn-rewind] v${pluginVersion()} active; workspace modes: git worktree, ordinary directory`)
    ctx.inject(['agents'], (scope: Context) => { checkpoints.install(scope) })
```

## 测试

快照含 `tests/engine.test.mjs`。本轮没有运行。

## 公司边界

本地文件回退可以参考。它不能回滚已经提交的云、超算或真机作业。账本不写入会话正文。
