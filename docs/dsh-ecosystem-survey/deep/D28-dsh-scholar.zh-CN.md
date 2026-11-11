# D28 · dsh-scholar

验证级别：静态阅读。提交 `086b19a2fbd7824dd71dde7ea2043f22888606e0`，提交时间 2026-09-10T05:48:21+08:00。没有运行上游测试，没有装入公司桌面。

目录卡片：D138。仓库：[lzszq/dsh-scholar](https://github.com/lzszq/dsh-scholar)。目录级判定是暂缓。

## 许可证

BSD 3-Clause。`LICENSE:1`。

## 调用链

`apply` 是异步的。注释要求先 `await sidecar.start()`，内核健康之后才登记工具和命令；启动失败则抛出，由宿主卸掉已登记资源。配置里有 `unattended`。阶段子代理默认 `enabled: false`，提供者是 `spawn`，深度上限 1。

## 证据锚

1. `LICENSE:1`
2. `LICENSE:3`
3. `src/plugin/index.ts:5-16`
4. `src/plugin/index.ts:313-323`
5. `src/plugin/index.ts:443-444`
6. `src/plugin/stage-subagents.ts:38-45`

## 引用

位置 `src/plugin/stage-subagents.ts:38-45`。

```
export const DEFAULT_STAGE_SUBAGENT_CONFIG: StageSubagentConfig = {
  enabled: false,
  provider: 'spawn',
  maxConcurrency: 4,
  maxFanoutPerAction: 6,
  maxDepth: 1,
  timeoutMs: 300_000,
  maxOutputBytes: 131_072,
```

## 测试

快照含 `tests/unit/analysis-determinism.test.ts`。本轮没有运行。

## 公司边界

文献检索的短摘录可以参考。这个提交的入口会拉起插件自己的内核侧车，并保留子代理面板。公司不接入这套研究操作系统，也不把子代理循环放进执行面。目录级「只借机制」收到深读后收紧为暂缓。
