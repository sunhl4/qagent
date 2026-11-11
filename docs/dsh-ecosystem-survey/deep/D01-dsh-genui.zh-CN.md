# D01 · dsh-genui

验证级别：静态阅读。提交 `8ed3999147d0d1a4815706d087a6f6e1fca9268f`，提交时间 2026-11-09T16:18:44+08:00。没有运行上游测试，没有装入公司桌面。

目录卡片：D022。仓库：[omdsh-dev/dsh-genui](https://github.com/omdsh-dev/dsh-genui)。目录级判定是暂缓。

## 许可证

MIT。`LICENSE:1` 为 MIT License。

## 调用链

宿主 `apply` 先安装原生通道，再向系统提示词写入 `genui:fence` 段。工具服务出现后，才登记 `render_ui` 与校验工具。没有工具服务时，围栏通道仍留在提示词里。

## 证据锚

1. `LICENSE:1`
2. `LICENSE:3`
3. `src/plugin/index.ts:216-218`
4. `src/plugin/index.ts:219-223`
5. `src/plugin/index.ts:228-233`
6. `tests/genui-quiz-guard.spec.ts:1`

## 引用

位置 `src/plugin/index.ts:228-233`。

```
  ctx.inject(['tools'], (toolsCtx) => {
    toolsCtx.effect(function* () {
      if (renderUiToolEnabled) {
        yield toolsCtx.tools.register(createRenderUiTool())
      }
      yield toolsCtx.tools.register(createValidateDshUiTool())
```

## 测试

快照含 `tests/genui-quiz-guard.spec.ts`。本轮没有运行。

## 公司边界

交互卡片可以留在上游界面扩展点。公司科学结果仍走短回执，不把可执行界面片段当成新的结果通道。
