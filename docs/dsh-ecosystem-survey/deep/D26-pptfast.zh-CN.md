# D26 · pptfast

验证级别：静态阅读。提交 `b1a2ab22b8b51ea6ccf048121a44d226128314c7`，提交时间 2026-10-23T14:55:13+08:00。没有运行上游测试，没有装入公司桌面。

目录卡片：D193。仓库：[liustack/pptwise](https://github.com/liustack/pptwise)。目录级判定是只借机制。

## 许可证

MIT。`LICENSE:1`。仓库目录名是 pptfast，包内插件名是 pptwise。

## 调用链

`apply` 依赖 skills 与 tools。预览、主题、大纲、构建和图片工具逐个登记，单个失败只跳过自己。注释写明运行时注册表不解析 SKILL.md 的 frontmatter，所以描述要单独作为注册字段。

## 证据锚

1. `LICENSE:1`
2. `LICENSE:3`
3. `dsh/index.js:44-45`
4. `dsh/index.js:51-55`
5. `dsh/index.js:191-208`
6. `src/dsh-client-card.test.tsx:1`

## 引用

位置 `dsh/index.js:191-208`。

```
  const preview = createPreviewService(CLI_PATH, ctx)
  try {
    ctx.tools.register(preview.tool)
  } catch (error) {
    console.error(`[pptwise] preview tool registration skipped: ${error}`)
  }
  // The theme wall and the one-pass build share the preview's store and
  // route: their cards fetch by id from the same place. Each registers on
  // its own, so one failing costs only itself.
  // The stock photo search shares no state with the preview service. It
  // takes the plugin's context to save its contact sheet as an attachment
  // the model can look at, where the host offers one.
  for (const tool of [preview.themesTool, preview.outlineTool, preview.buildTool, createImagesTool(CLI_PATH, ctx)]) {
    try {
      ctx.tools.register(tool)
    } catch (error) {
      console.error(`[pptwise] ${tool.name} tool registration skipped: ${error}`)
    }
```

## 测试

快照含 `src/dsh-client-card.test.tsx`。本轮没有运行。

## 公司边界

演示文稿的预览和版式可以对照 `company_office_create` 与 WPS。不另做第二套图表渲染器，也不把整份 PPTX 正文回进会话。
