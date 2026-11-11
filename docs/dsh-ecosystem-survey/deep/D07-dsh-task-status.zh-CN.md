# D07 · dsh-task-status

验证级别：静态阅读。提交 `3751096f38eeb52df85b2cfae15a239d4197d643`，提交时间 2026-10-03T09:54:00-07:00。没有运行上游测试，没有装入公司桌面。

目录卡片：D092。仓库：[vlln/dsh-task-status](https://github.com/vlln/dsh-task-status)。目录级判定是暂缓。

## 许可证

MIT。`LICENSE:1`。

## 调用链

`apply` 换掉 `ctx.jobs.read`。注释说明镜像返回官方尚未消费的增量，直读再补 producer 未读的增量，避免插件自己的读取吃掉官方游标。

## 证据锚

1. `LICENSE:1`
2. `LICENSE:3`
3. `src/index.mjs:126-129`
4. `src/index.mjs:130-133`
5. `src/index.mjs:134-142`
6. `cordis.patch.yml:1`

## 引用

位置 `src/index.mjs:126-142`。

```
export function apply(ctx) {
  ctx.effect(() => {
    // 绑定底层原始 read（插件自读经 rawRead 绕过补丁）。
    rawRead = ctx.jobs.read.bind(ctx.jobs)
    // 镜像补丁（镜像 + 直读补最新）：官方 read = 缓冲中"官方未消费"的增量
    // （别人已读的，镜像返回，不重复消耗 producer 游标）+ 直读"producer 未读"
    // 的最新增量（正常消耗）。官方视图完整无滞后、无重复；每个增量恰好被
    // 消耗一次（插件自读或官方直读），双方都能看到全量。
    ctx.jobs.read = (id, caller) => {
      const buf = outputBuffers.get(id)
      const consumed = officialConsumed.get(id) ?? 0
      const mirror = buf !== undefined && buf.length > consumed ? buf.slice(consumed) : ''
      // 直读补最新：消耗 producer 游标（拿自官方上次 read 以来新产出的增量），
      // 同时累积进缓冲（插件视图也完整）。
      const result = rawRead(id, caller)
      accumulate(id, result?.text)
      const text = mirror + (result?.text ?? '')
```

## 测试

扫描没有找到测试文件。

## 公司边界

后台任务的进度条适合上游会话页。公司不另做第二套任务运行器。进度文本保持短，不回放完整命令输出。
