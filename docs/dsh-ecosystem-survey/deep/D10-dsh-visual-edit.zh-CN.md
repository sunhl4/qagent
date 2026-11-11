# D10 · dsh-visual-edit

验证级别：静态阅读。提交 `43c72d25bcb52e55c0ee332b741dd5293d1987eb`，提交时间 2026-10-02T12:32:35+08:00。没有运行上游测试，没有装入公司桌面。

目录卡片：D056。仓库：[Han-1413141/dsh-visual-edit](https://github.com/Han-1413141/dsh-visual-edit)。目录级判定是思想可取。

## 许可证

MIT。`LICENSE:1`。

## 调用链

宿主 `apply` 为空。文件注释写明宿主一半没有工具，也没有文件系统，界面使用 DSH 自己的输入框。

## 证据锚

1. `LICENSE:1`
2. `LICENSE:3`
3. `src/index.ts:1-2`
4. `src/client/index.tsx:1`
5. `cordis.patch.yml:1`
6. `test/core.test.ts:1`

## 引用

位置 `src/index.ts:1-2`。

```
/** The host half has no tools or filesystem access. The UI uses DSH's native composer. */
export function apply(): void {}
```

## 测试

快照含 `test/core.test.ts`。本轮没有运行。

## 公司边界

选区批注留在上游客户端。公司不为批注增加工具，也不把页面元素正文送进科学结果。
