# D08 · ikanban

验证级别：静态阅读。提交 `77b76a737ef07478cc95b0e341a88f027716c66b`，提交时间 2026-11-02T00:22:37+08:00。没有运行上游测试，没有装入公司桌面。

目录卡片：D098。仓库：[isomoes/ikanban](https://github.com/isomoes/ikanban)。目录级判定是暂缓。

## 许可证

MIT。`LICENSE:1`。

## 调用链

文档把 v0.4 起的产品写成 DSH Web 组合包插件，安装 `@isomoes/dsh-ikanban` 后由一个 profile 启动完整应用。本次提交 `77b76a737ef07478cc95b0e341a88f027716c66b` 的工作树里没有 `cordis.patch.yml`。文档描述的组合文件和这次快照的文件集合不一致。

## 证据锚

1. `LICENSE:1`
2. `LICENSE:3`
3. `docs/0.4.2.md:3`
4. `docs/0.4.2.md:7`
5. `docs/0.4.2.md:11-12`
6. `packages/session-ui/src/import-boundaries.test.ts:1`

## 引用

位置 `docs/0.4.2.md:7-12`。

```
从 `v0.4.0` 开始，iKanban 被重新实现为 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 的 Web 组合包插件。用户安装 `@isomoes/dsh-ikanban` 后，通过一个 DSH profile 启动完整应用，而不是单独启动 iKanban 前端和后端。

`v0.4.2` 的核心定位如下：

- 复用 DSH 的 agent、会话、工具、存储、workspace、API 网关和 Web server 等宿主能力。
- 由 iKanban 提供 Web 启动入口、运行时胶水、浏览器目录选择器和完整浏览器界面。
```

## 测试

快照有 Web 测试，例如 `packages/session-ui/src/import-boundaries.test.ts`。它们不证明缺失的组合补丁已经存在。本轮没有运行。

## 公司边界

键盘优先的任务板可以作注意力面板的界面参考。本仓库不并行一套 Web 宿主，也不把多代理工作区接进公司执行面。目录级判定维持暂缓。
