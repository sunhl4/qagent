# D22 · REMI

验证级别：静态阅读。提交 `e19ba5533666402cbd4ff1932f24aec2fb8f97da`，提交时间 2026-10-22T23:14:30+08:00。没有运行上游测试，没有装入公司桌面。

目录卡片：D148。仓库：[Hoshino910/REMI](https://github.com/Hoshino910/REMI)。目录级判定是暂缓。

## 许可证

MIT。`LICENSE:1`。

## 调用链

`apply` 构造 `DshSelectiveMemory`。它订阅 `session/event` 把观察排进队列，并在用户消息到达时累计本回合查询。`turn/end` 删掉查询窗口。

## 证据锚

1. `LICENSE:1`
2. `LICENSE:3`
3. `packages/dsh-adapter/src/index.ts:237-240`
4. `packages/dsh-adapter/src/index.ts:242-252`
5. `packages/dsh-adapter/src/index.ts:428-430`
6. `packages/dsh-adapter/tests/window.test.ts:1`

## 引用

位置 `packages/dsh-adapter/src/index.ts:237-252`。

```
    ctx.on('session/event', (session, event) => {
      this.enqueueObservation(session, event)
      if (event.type === 'turn/end') this.queryWindows.delete(String(session.id))
    })

    ctx.on('agent/inbox/claimed', ({ agent, message, turn }) => {
      if (message.source.kind !== 'user') return
      const query = contentToText(message.content)
      if (query.length === 0) return
      const sessionId = String(agent.session.id)
      const current = this.queryWindows.get(sessionId)
      this.queryWindows.set(sessionId, {
        turn,
        query: current?.turn === turn ? `${current.query}\n${query}` : query,
      })
    })
```

## 测试

快照含 `packages/dsh-adapter/tests/window.test.ts`。本轮没有运行。

## 公司边界

自动观察会话并准备注入，目录级暂缓维持。公司不把会话正文写进记忆库，也不子类化压缩引擎。
