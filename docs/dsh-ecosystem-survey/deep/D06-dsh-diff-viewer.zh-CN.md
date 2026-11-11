# D06 · dsh-diff-viewer

验证级别：静态阅读。提交 `c46f11b144fff7f1191d22c391f455b3f8f650c9`，提交时间 2026-10-19T22:59:55+08:00。没有运行上游测试，没有装入公司桌面。

目录卡片：D015。仓库：[lehhair/dsh-diff-viewer](https://github.com/lehhair/dsh-diff-viewer)。目录级判定是只借机制。

## 许可证

根目录没有 LICENSE 文件。`package.json:80` 写明 BSD-3-Clause。许可文本未随这个快照的根文件提供。

## 调用链

`apply` 监听 `agent/created`，取出该代理层上的 `edit` 与 `write`，再用包一层的工具登记回去。同一层里已经有阴影时，第二次跳过，避免注册表拒绝同名登记。

## 证据锚

1. `package.json:8`
2. `package.json:80`
3. `src/index.ts:154-156`
4. `src/index.ts:159-164`
5. `src/index.ts:166-172`
6. `tests/diff-viewer.spec.tsx:1-6`

## 引用

位置 `src/index.ts:164-172`。

```
          const original = agent.ctx.tools.get(name, agent as object)
          if (original === undefined) continue
          // Guard against a double-install (plugin reload, or two diff-viewer
          // copies in one composition): re-registering the same name in the
          // same layer is what the registry rejects, so a second effect that
          // finds the FIRST shadow already visible skips instead of throwing.
          const current = agent.ctx.tools.get(name, agent as object)
          if (current !== undefined && current !== original) continue
          disposers.push(agent.ctx.tools.register(enhanceTool(original)))
```

## 测试

快照含 `tests/diff-viewer.spec.tsx`，文件头说明它测的是差异计算和渲染。本轮没有运行。

## 公司边界

差异视图替换的是工具结果的呈现，适合留在上游界面。公司不为此新做一套文件写入工具。
