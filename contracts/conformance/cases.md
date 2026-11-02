# 一致性用例

双方实现都必须通过同一组用例。用例编号稳定，不允许复用或删除。

## 1. IdentityPort

### ID-01 正常校验

- 输入：有效 token
- 期望：返回 subject，含 tenantId 与 scopes
- 失败：抛出 `INVALID_REQUEST` 或 `POLICY_DENIED`

### ID-02 过期 token

- 输入：过期 token
- 期望：`POLICY_DENIED`，不可重试

### ID-03 跨租户

- 输入：tenant A 的 token，期望 tenant B
- 期望：`POLICY_DENIED`

### ID-04 签发 Agent grant

- 输入：taskId、scopes、ttl、maxCost
- 期望：grant 绑定 taskId，带过期时间
- 失败：scope 超出父主体权限 → `POLICY_DENIED`

### ID-05 撤销

- 输入：已签发的 grantId
- 期望：撤销后使用该 grant 的调用立即失败

## 2. ObjectStorePort

### OS-01 写入并读回

- 输入：body + sha256
- 期望：返回 artifact.uri 与 sha256；读回内容一致

### OS-02 哈希不匹配

- 输入：body 的 sha256 与声明不一致
- 期望：`INVALID_REQUEST`，不落盘

### OS-03 大对象

- 输入：超过内联阈值的 body
- 期望：拒绝内联或转为外部分片，不得静默截断

### OS-04 不存在

- 输入：不存在的 uri
- 期望：`NOT_FOUND`

### OS-05 预签名

- 输入：read + ttl
- 期望：返回 URL 与过期时间；过期后不可用

## 3. CredentialsPort

### CR-01 签发

- 输入：subject、audience、actions、ttl
- 期望：返回 token，TTL 不超过请求值

### CR-02 超权限

- 输入：actions 超出 subject scopes
- 期望：`POLICY_DENIED`

### CR-03 长期密钥

- 输入：请求包含明文长期密钥
- 期望：`INVALID_REQUEST`

### CR-04 撤销

- 输入：已签发 token
- 期望：撤销后立即失效

## 4. ModelPort

### MD-01 普通补全

- 输入：messages、maxOutputTokens
- 期望：返回 content、modelId、modelVersion、usage

### MD-02 结构化输出

- 输入：responseSchema
- 期望：content 可解析且符合 schema；否则 `INTERNAL`

### MD-03 数据等级

- 输入：dataClass=restricted，实现仅支持 internal
- 期望：`POLICY_DENIED`，不得降级到外部模型

### MD-04 流式不支持

- 输入：stream
- 期望：`NOT_SUPPORTED`，不得返回非流式结果冒充流式

### MD-05 回退

- 输入：preferredModelId 不可用
- 期望：返回 fallbackFrom，并在 usage 中记录

## 5. HpcPort / CloudPort

### HP-01 提交

- 输入：合法 JobRequest
- 期望：返回 jobId 与 submitted 状态

### HP-02 幂等

- 输入：同 idempotencyKey 重复提交
- 期望：返回同一 jobId，不重复创建

### HP-03 报价

- 输入：JobRequest
- 期望：返回估计值与 feasible；不可行时给出原因

### HP-04 取消

- 输入：running job
- 期望：返回 cancelled 或明确 `CONFLICT`

### HP-05 未知执行

- 输入：无法确认是否执行的 job
- 期望：返回 `unknown_execution`；上层不得重试

### HP-06 日志

- 输入：jobId、tailLines
- 期望：返回行数组与 truncated 标记

### HP-07 对账

- 输入：jobId
- 期望：返回真实状态；无法判断时返回 `unknown_execution`

## 6. SessionPort

### SS-01 启动

- 输入：SessionRequest
- 期望：返回 sessionId，状态 started 或 queued

### SS-02 事件顺序

- 输入：正常会话
- 期望：turn_started → message/tool_* → turn_finished，顺序单调

### SS-03 预算超限

- 输入：超过 maxCost
- 期望：状态 budget_exceeded，停止后续 turn

### SS-04 取消

- 输入：running 会话
- 期望：状态 cancelled，事件停止

### SS-05 工具越权

- 输入：调用不在 allowedTools 的工具
- 期望：事件 error + 状态 failed 或继续但记录拒绝

### SS-06 会话不是事实源

- 输入：会话完成
- 期望：业务状态仍由平台记录；会话结果只作为输入

## 7. TelemetryPort

### TL-01 脱敏

- 输入：含敏感字段的 attributes
- 期望：实现必须拒绝或脱敏，并标记 redactionApplied

### TL-02 高基数

- 输入：随机 jobId 作为指标标签
- 期望：拒绝或改为日志字段

## 8. 跨端口

### XP-01 端到端

- 流程：identity → grant → credentials → hpc.submit → status → object.put → manifest
- 期望：每步都有 traceId 与幂等键；失败可定位

### XP-02 未知执行不再提交

- 流程：hpc.status 返回 unknown → 上层尝试重试
- 期望：被策略拒绝

### XP-03 降级声明

- 流程：加载 stub
- 期望：manifest.degraded=true，且要求 degradedReason
