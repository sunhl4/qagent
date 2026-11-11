# D03 · dsh-side-panel

验证级别：静态阅读。提交 `baca7806714ac577ac529647f105d58a2a10b228`，提交时间 2026-08-15T01:45:30+08:00。没有运行上游测试，没有装入公司桌面。

目录卡片：D045。仓库：[ccq1/dsh-side-panel](https://github.com/ccq1/dsh-side-panel)。目录级判定是暂缓。

## 许可证

BSD 3-Clause。`LICENSE:1`。

## 调用链

`apply` 在内存里保存终端进程表，并在回合开始和结束时对工作目录做 git 差异快照。同一函数还向 web 服务登记文件浏览路由。

## 证据锚

1. `LICENSE:1`
2. `LICENSE:3`
3. `src/index.ts:158-162`
4. `src/index.ts:165-176`
5. `src/index.ts:177-180`
6. `tests/file-browser.spec.ts:1`

## 引用

位置 `src/index.ts:158-176`。

```
export function apply(ctx: HostContext, config: Config = {}): void {
  const maxText = config.maxTextBytes ?? 2 * 1024 * 1024
  const maxImage = config.maxImageBytes ?? 10 * 1024 * 1024
  const searchMaxResults = config.searchMaxResults ?? 200
  const terminals = new Map<string, { owner: string; process: ChildProcessWithoutNullStreams; chunks: string[]; exited: boolean }>()
  const turnGit = new Map<string, TurnGitState>()
  let nextTerminal = 0
  ctx.on('session/event' as never, ((session: SessionRecord, event: { type: string }) => {
    if (event.type !== 'turn/start' && event.type !== 'turn/end') return
    const cwd = session.header.cwd
    if (cwd === undefined) return
    const state = turnGit.get(session.id) ?? { ready: Promise.resolve() }
    state.ready = state.ready.then(async () => {
      const snapshot = await workspaceDiff(resolve(cwd))
      if (event.type === 'turn/start') state.before = snapshot
      else if (state.before !== undefined) { state.last = changedDiff(state.before, snapshot); state.before = undefined }
    }).catch(() => {})
    turnGit.set(session.id, state)
  }) as never)
```

## 测试

快照含 `tests/file-browser.spec.ts`。本轮没有运行。

## 公司边界

文件树和差异展示可以参考。插件自管终端进程是另一条执行面，公司开发桌面继续用上游标准预设里已有的壳，不把这张进程表接进来。
