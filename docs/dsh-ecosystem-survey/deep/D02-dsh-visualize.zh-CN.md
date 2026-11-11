# D02 · dsh-visualize

验证级别：静态阅读。提交 `af4efe7a59a36d4562b340ff50d771d2691cdc8c`，提交时间 2026-11-07T18:55:28Z。没有运行上游测试，没有装入公司桌面。

目录卡片：D057。仓库：[Nagi-ovo/dsh-visualize](https://github.com/Nagi-ovo/dsh-visualize)。目录级判定是暂缓。

## 许可证

BSD 3-Clause。`LICENSE:1`。

## 调用链

`apply` 把 `visualize` 登记到 `ctx.tools`，并把同名技能登记到 `ctx.skills`。样式变更时先卸掉旧工具再登记。文件头写明没有浏览器半边时，退回工具的普通文本。

## 证据锚

1. `LICENSE:1`
2. `LICENSE:3`
3. `src/index.ts:1-7`
4. `src/index.ts:75-78`
5. `src/index.ts:82-90`
6. `tests/shell.spec.ts:1`

## 引用

位置 `src/index.ts:82-90`。

```
  let disposeTool = ctx.tools.register(visualizeTool(ctx, config.maxFragmentBytes, style, images))
  const events = ctx as unknown as { on(name: 'loader/volatile-update', listener: () => void): unknown }
  events.on('loader/volatile-update', () => {
    if (style() === toolStyle) return
    disposeTool()
    toolStyle = style()
    disposeTool = ctx.tools.register(visualizeTool(ctx, config.maxFragmentBytes, style, images))
  })
  ctx.skills.registerProvider(() => visualizeSkillProvider(style, cwd => styleFileLocations(ctx, cwd)))
```

## 测试

快照含 `tests/shell.spec.ts`。本轮没有运行。

## 公司边界

流式预览和沙箱卡片适合上游界面。公司座席只保留短文本回退，不把 HTML 卡片当作科学结果。
