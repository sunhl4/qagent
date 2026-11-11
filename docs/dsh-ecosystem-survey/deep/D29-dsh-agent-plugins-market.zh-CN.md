# D29 · dsh-agent-plugins-market

验证级别：静态阅读。提交 `eea27127c65fd3d2451a5fcc544a7f202f221ef2`，提交时间 2026-11-09T15:31:05+08:00。没有运行上游测试，没有装入公司桌面。

目录卡片：D210。仓库：[Sivan757/dsh-agent-plugins-market](https://github.com/Sivan757/dsh-agent-plugins-market)。目录级判定是只借机制。

## 许可证

MIT。`LICENSE:1`。

## 调用链

`apply` 解析用户根和数据根，并装配运行时调和器。安装测试的注释写明安装即启用，安装前对话框是确认门，禁用会停止注入，卸载会清掉状态。

## 证据锚

1. `LICENSE:1`
2. `LICENSE:3`
3. `packages/market-bundle/src/index.ts:177-193`
4. `packages/market-bundle/test/install-gate.test.ts:9-14`
5. `cordis.patch.yml:1`
6. `packages/market-bundle/src/index.ts:254-256`

## 引用

位置 `packages/market-bundle/test/install-gate.test.ts:9-14`。

```
 * Install lifecycle regression tests (dsh-web PR #1098 review).
 *
 * Model: install == enable (the pre-install dialog is the confirmation
 * gate; cancel never reaches the host). The safety property lives in the
 * lifecycle: disabling stops injection, uninstalling clears everything,
 * and state round-trips across reloads.
```

## 测试

`packages/market-bundle/test/install-gate.test.ts` 描述安装即启用。本轮没有运行。

## 公司边界

市场页上的已安装状态和禁用即停注入可以参考。外部技能、hooks 和 MCP 不注入命令行的 system-trust 组合。
