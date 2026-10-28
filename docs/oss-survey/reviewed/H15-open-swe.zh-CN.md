# H15 open-swe：事件去重与并发限额复核

- 项目：`langchain-ai/open-swe`。
- SHA：`794eaa72bff2ac90c7e394bd0a9056cf16d488d4`。
- 提交：2026-10-22T03:57:30+00:00。
- 来源：`/tmp/oss-langchain-ai-open-swe`。
- 许可：根 LICENSE 为 **MIT**；旧速评的 AGPL 判断错误，撤回。
- 验证：静态源码、SQL 与测试阅读，未运行数据库/模型。

## 定位与范围

当前仓库含完整编码服务、前端、bridge 与业务事件处理。
本次聚焦对公司平台回调/重复提交有价值的 event_claims，而非引入整套 Agent。
它给出数据库层去重与限额控制的具体实现，也暴露 exactly-once 的适用边界。

## 主调用链

业务 handler 在处理 `(scope,key)` 事件前调用 `claim()`。
函数开启数据库 transaction，先清理少量过期记录，再执行原子 INSERT/ON CONFLICT。
成功 RETURNING 1 表示本次取得 claim；否则已有有效持有者。
处理在副作用前失败可 release，让后续重送重新取得。
需要组限额的场景调用 `claim_within_limit()`，先加组事务锁再计数和领取。
证据：`openswe/event_claims.py:1-49,93-129`。

## 一：数据库原子冲突更新避免先查后插竞态

_CLAIM 以 scope/key 唯一冲突为基础。
冲突只在旧记录 expires_at 已过期时允许更新。
相比应用层先 SELECT 再 INSERT，这个条件与写操作在同一 SQL 中。
claim 带 TTL，可以处理 holder 崩溃而不释放的情况。
证据：`openswe/event_claims.py:20-29`。

```23:27:openswe/event_claims.py
    INSERT INTO event_claim (scope, key, expires_at)
    VALUES (:scope, :key, clock_timestamp() + CAST(:ttl AS interval))
    ON CONFLICT (scope, key) DO UPDATE
        SET claimed_at = clock_timestamp(), expires_at = clock_timestamp() + CAST(:ttl AS interval)
        WHERE event_claim.expires_at <= clock_timestamp()
```

## 二：清理有界、锁跳过降低争用

_SWEEP 每次只删有限过期项，使用 LIMIT 与 FOR UPDATE SKIP LOCKED。
这样领取事件不会为了扫全表被长时间阻塞，也避免与其他领取者抢同一批锁。
这属于事件表维护，不证明无限负载下仍满足延迟 SLA。
证据：`event_claims.py:30-41`。

对公司而言，回调去重表必须有保留时长、索引和监控，而不是无限增长的 JSONL。
删除去重记录的时间应与平台重送窗口一致，否则过期事件可能再被受理。

## 三：限额检查与领取共享同一事务

`claim_within_limit()` 获取 `pg_advisory_xact_lock(hashtext(...))`。
组内最近窗口的 claim 数量达到 limit 返回 limited。
否则执行同一 _CLAIM，返回 claimed 或 taken。
测试用 5 个并发请求、limit=2，断言两个成功、三个 limited。
证据：`event_claims.py:103-129`、`tests/agent/test_event_claims.py:27-42`。

这是模型调用配额/回调并发的机制参考，不能代替云/HPC 的最终配额与收费记录。

## 四：claim 的 exactly-once 不是外部执行 exactly-once

文件头说明副作用前失败才 release；TTL 到期后本来就允许重新领取。
如果平台已经接受 QPU 作业但网络回包丢失，事件 claim 不能知道物理副作用是否发生。
公司 request_id 合同明确不是幂等键，因此不能仅凭 claim 过期自动重交。
正确做法是查询平台事实并保持 unknown，必要时用户重新确认。

`defer()` 用 greatest 只延长 cooldown 不缩短，避免并发短值覆盖长值。
`held()` 与 `remaining()` 可读当前状态，但不能充当外部平台运行状态。
证据：`event_claims.py:52-90`。

## 测试证据

`tests/agent/test_event_claims.py:16-24` 测重复 claim 失败、过期清理、release 后可重取。
`:27-42` 检查组锁控制的并发上限。
`:45-55` 验证 defer 不缩短以及到期归零。
这些是数据库集成测试，依赖 registry_db fixture；本轮没有执行。
它们没有验证真实量子/HPC 端到端幂等，不能把结果扩大。

## 公司落点

1. 回调适配层可参考 scope+key 去重，键必须绑定用户/租户和业务服务，避免跨域碰撞。
2. 新合同先定义受理与完成、重复请求、过期与未知状态，再写 Python adapter。
3. 插件只透传受管短结果，不自行在会话层实现 retry loop。
4. `tests/test_contract_upgrade.py` 已有设备 timeout unknown，继续保留零重试约束。
5. 新故障用例：已受理但响应丢失、TTL 到期重复 webhook、数据库断连、并发同键。

## 不能采用

不能引入 open-swe 的生产模型循环、自动 shell 执行或默认远程凭据链。
也不能因 MIT 就跳过依赖、遥测、租户数据流审查。
本次只核查事件 claim 子系统，其余服务不作全面安全声明。

## 结论

可借的是数据库原子去重、有限清理和组事务锁。
不可借的是把本地 event claim 宣称为物理设备 exactly-once。
许可纠错为 MIT，并记录实际快照，不再沿用旧速评标签。

## 证据

- `LICENSE:1-21`。
- `openswe/event_claims.py:1-49,52-90,93-129`。
- `tests/agent/test_event_claims.py:16-24,27-42,45-55`。
