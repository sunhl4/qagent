# D15 · dsh-riskproof

验证级别：静态阅读。提交 `514746afe1d07889890737fda20d6107731c8a06`，提交时间 2026-10-27T21:37:22+08:00。没有运行上游测试，没有装入公司桌面。

目录卡片：D112。仓库：[onlyqzq/dsh-riskproof](https://github.com/onlyqzq/dsh-riskproof)。目录级判定是只借机制。

## 许可证

Apache-2.0。`LICENSE:2` 起是 Apache 许可正文。

## 调用链

`apply` 同时挂上执行前、执行后、结果、工具变更和代理释放。`preExecute` 在 `mode === "observe"` 时，即使判定是 deny 或 ask，仍然 `await next()`。enforce 模式下 deny 直接返回，ask 与后续瀑布合并。原因字符串里带上来源工具链。

## 证据锚

1. `LICENSE:2-3`
2. `src/index.ts:8-13`
3. `src/index.ts:44-51`
4. `src/dsh/runtime.ts:88-96`
5. `src/dsh/runtime.ts:102-111`
6. `src/dsh/engine-policy.ts:6-18`

## 引用

位置 `src/dsh/runtime.ts:102-111`。

```
    if (this.config.mode === "observe" && mine.kind !== "allow") {
      this.logger.warn(
        `[observe] would ${mine.kind === "deny" ? "deny" : "ask"} tool '${exec.name}': ${decision.reason}`,
      );
    }

    try {
      const effective = this.config.mode === "observe" || mine.kind === "allow"
        ? await next()
        : mine.kind === "deny" ? mine : mergePreToolDecisions(mine, await next());
```

## 测试

快照含 `tests/dsh-mocks.ts`。本轮没有运行。

## 公司边界

出处链可以作策略说明的参考。observe 下放行不能进入公司。批准仍由现有授权卡承担，不另做证明存储。
