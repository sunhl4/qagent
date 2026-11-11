# D04 · dsh-ui-hub

验证级别：静态阅读。提交 `219fe63a65de64bf4720bd0b9ec47b4a9c05d4c5`，提交时间 2026-10-02T12:32:28+08:00。没有运行上游测试，没有装入公司桌面。

目录卡片：D054。仓库：[Han-1413141/dsh-ui-hub](https://github.com/Han-1413141/dsh-ui-hub)。目录级判定是思想可取。

## 许可证

MIT。`LICENSE:1`。

## 调用链

宿主 `apply` 是空函数，不登记工具。浏览器半边只给已有 DOM 加 `data-uihub-*` 属性，用自己的样式表调整位置。去掉属性后，原布局按注释所述恢复。

## 证据锚

1. `LICENSE:1`
2. `LICENSE:3`
3. `lib/index.js:19`
4. `lib/client.js:1-3`
5. `lib/client.js:4-10`
6. `test/verify_layout.py:1`

## 引用

位置 `lib/client.js:4-10`。

```
 * A layout butler for every plugin UI in the DSH web client. It never changes
 * how plugins render: it only discovers their DOM, then drives three additive
 * attributes (`data-uihub-off`, `data-uihub-nudge`, `data-uihub-float`) whose
 * effect comes entirely from this bundle's own `!important` stylesheet rules.
 * Inline `left/top` writes from other plugins therefore cannot override an
 * enforced position (their non-important inline styles lose to our important
 * rules), and removing the attributes restores the original layout bit-for-bit.
```

## 测试

快照含 `test/verify_layout.py`。本轮没有运行。

## 公司边界

布局管家适合作为上游界面的附加层。公司仓库不另写对话壳，也不让布局插件获得文件或工具权限。
