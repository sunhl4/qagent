# D24 · docindex

验证级别：静态阅读。提交 `ce0bb5f394eee249e72535934c64e48a2cf1a5b8`，提交时间 2026-10-16T00:00:51+08:00。没有运行上游测试，没有装入公司桌面。

目录卡片：D129。仓库：[JohnXu22786/docindex](https://github.com/JohnXu22786/docindex)。目录级判定是只借机制。

## 许可证

MIT。`LICENSE:1`。

## 调用链

服务 `init` 时把 `createDocTools` 的每个定义登记到 `ctx.tools`。配置为 watch 时，引擎回调只打新增、更新和删除的计数。补丁注释写明后层补丁会整段替换 `config`。

## 证据锚

1. `LICENSE:1`
2. `LICENSE:3`
3. `cordis.patch.yml:1-6`
4. `src/index.ts:146-149`
5. `src/index.ts:150-156`
6. `test/plugin.test.ts:10-14`

## 引用

位置 `test/plugin.test.ts:10-14`。

```
test('plugin: default export is a Service subclass class', () => {
  assert.equal(typeof DocIndexService, 'function')
  assert.ok(DocIndexService.prototype, 'class has a prototype')
  assert.ok(Array.isArray((DocIndexService as { inject?: string[] }).inject), 'declares inject')
  assert.deepEqual((DocIndexService as { inject?: string[] }).inject, ['tools'])
```

## 测试

`test/plugin.test.ts` 断言默认导出声明 `inject` 为 `tools`。本轮没有运行。

## 公司边界

工作区文档索引和计数日志可以参考。工具是否可见仍由公司合同决定。索引命中不提高原文的可见范围。
