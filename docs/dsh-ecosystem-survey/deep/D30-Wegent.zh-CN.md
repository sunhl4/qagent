# D30 · Wegent

验证级别：静态阅读。提交 `1149631ab4df6f7ed1e66f0c1599b4aeb5fb2a79`，提交时间 2026-11-10T19:30:25Z。没有运行上游测试，没有装入公司桌面。

目录卡片：D104。仓库：[wecode-ai/Wegent](https://github.com/wecode-ai/Wegent)。目录级判定是暂缓。

## 许可证

Apache-2.0。`LICENSE:1` 起是 Apache 许可标题。

## 调用链

README 把产品写成人和 AI 围绕同一 Issue 推进的工作系统，并提供桌面下载。抽查的 DSH 插件入口 `wework/dsh/ui-home-focus/index.js` 与 `wework/dsh/ui-git/index.js` 都是空的 `apply`。这次快照里，座席信息架构在更大的应用里，不在这两个插件入口的工具登记里。

## 证据锚

1. `LICENSE:1-3`
2. `README.md:1`
3. `README.md:13`
4. `wework/dsh/ui-home-focus/index.js:1-2`
5. `wework/dsh/ui-git/index.js:1-2`
6. `backend/app/services/plugin_build_attestation.py:1`

## 引用

位置 `README.md:13`。

```

```

## 测试

快照含大量后端测试。抽到 `backend/app/services/plugin_build_attestation.py` 作为文件存在的锚点。本轮没有运行。

## 公司边界

Issue 把讨论、执行和交付放在一起，这个信息架构可以参考上游注意力面板。公司不采用另一套桌面壳，也不把空插件入口当成可登记工具。目录级暂缓维持。
