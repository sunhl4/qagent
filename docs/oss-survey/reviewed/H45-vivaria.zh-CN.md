# H45 Vivaria：评估运行清理与失败事实复核

- 项目：`METR/vivaria`。
- SHA：`20a6c290c3c11f701af95a559d9d0c64dd6105d4`；提交2026-02-15T15:51:13-08:00。
- 来源：`/tmp/oss-METR-vivaria`。
- 根 `LICENSE:1-21` 是 MIT，旧速评标 Apache-2.0 有误。
- 验证：静态阅读，未启动 Docker/DB/云资源；提交日期不等于停维声明。

## 聚焦链路

`RunKiller.killBranchWithError()` 先读 agent PID。
没有 PID 就转 `killRunWithError()`；已有进程时先记录 fatal error，再在 finally 清理。
仅余当前分支时调用 maybeCleanupRun；仍有其他分支时仅 kill 当前进程组。
`killRunWithError()` 同样保证无论数据库记录如何，finally 执行清理尝试。
证据：`server/src/services/RunKiller.ts:28-70`。

## 机制一：错误记录不覆盖原始事实

`setFatalErrorIfAbsent` 只在此前无 fatal error 时设置，返回是否首次记录。
Slack 通知只在首次设置且策略允许时触发，避免重复告警。
通知通过 background 执行，不把通知成功视为业务清理已成功。
这对公司回执有启发：任务失败原因、审计记录和通知状态应分别存在。

## 机制二：分支资源与运行资源不同

countOtherRunningBranches 决定只停一个进程组还是清理整次 run。
粗暴删除共享容器会伤害其他运行分支，因此资源所有权需要明示。
公司对应的是平台作业与用户会话的关系：关闭对话不代表有权取消其所有历史资源。
证据：`RunKiller.ts:49-58,104-110`。

## 机制三：保留环境是显式条件

`maybeCleanupRun` 读取 keepTaskEnvironment 标志，未要求保留才 cleanupRun。
它随后检查 batch 是否还有 running、paused、queued、settingUp 项，避免提前释放批次资源。
这一条件不能直接套到 QPU：设备副作用不能被容器清理撤销，取消需要调用平台事实接口。
证据：`RunKiller.ts:114-138`。

```65:70:server/src/services/RunKiller.ts
  async killRunWithError(host: Host, runId: RunId, error: RunError) {
    try {
      await this.killUnallocatedRun(runId, error)
    } finally {
      await this.maybeCleanupRun(host, runId)
    }
```

## 恢复不等于抹除执行历史

`resetBranchCompletion()` 清空当前完成/评分字段，同时调用 updateWithAudit 记录 userId 和 reason='unkill'。
可借“恢复动作本身也留痕”，不能借“清空字段”来伪装外部作业未执行。
公司必须保留未知或已派发事实，不以恢复请求为依据重交设备任务。
证据：`RunKiller.ts:87-101`。

## 测试与边界

`RunKiller.test.ts:29-47` 对无 agentPid 场景断言转到 killRunWithError。
`:49-77` 验证最后分支清理且数据库 fatalError 正确保存。
这些测试受 INTEGRATION_TESTING 环境条件控制，需要数据库 fixture；本轮没有运行。
它们不证明隔离环境无逃逸，也不证明云资源清理不会失败。

## 公司映射

1. `contracts/results.json` 继续区分 not_dispatched/dispatched/completed/unknown；清理结果另记。
2. Python adapter 查询平台真实状态，取消“请求受理”与“取消完成”分离。
3. 插件/工作台可显示重试或恢复的人工动作，但不自行重放副作用。
4. 测试包含取消失败、回执写入失败、并行任务共享资源、会话断开但任务继续。

## 结论

Vivaria 是隔离评估运行器的参考，不作为生产 Agent runtime。
最有价值的是 finally 清理、首错保留和资源归属；本篇不对全部评测系统作安全认证。

## 证据

`LICENSE:1-21`；`server/src/services/RunKiller.ts:28-58,62-83,87-110,114-138`；`server/src/services/RunKiller.test.ts:29-77`。
