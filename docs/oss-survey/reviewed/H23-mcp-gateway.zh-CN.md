# H23 Docker MCP Gateway：策略默认值与治理边界复核

- 项目：`docker/mcp-gateway`。
- SHA：`2f72d7905acf1d88810b215c948e78384f849dcf`；提交 2026-10-21T10:11:06-04:00。
- 来源：`/tmp/oss-docker-mcp-gateway`。
- 验证：静态阅读，未启动 Docker Desktop、MCP 服务或外部目录。

## 核心纠错

旧稿把 catalog/profile/secret 的组合描述为与公司治理“完全同构”，但源码存在明确的默认允许策略客户端。机制可以借鉴，默认部署安全语义不能直接继承。

## 真实策略调用结构

`pkg/policy/policy.go` 定义 ActionLoad、ActionInvoke、ActionPrompt，并把 catalog、workingSet、server、transport、tool 和 target 装进 Request。
客户端接口包含单次 Evaluate、批量 EvaluateBatch 和 SubmitAudit，允许在装载期和执行期评价同一类请求。
这比只在 tools/list 过滤更完整，但调用方是否实际使用以及选到什么 client 必须一起核验。

## 三个实现细节

1. Request 把服务器来源和传输协议显式携带，可支持本地/远程差异策略。公司 provider 与 preset 同样应来自可信配置而非模型参数。
2. Decision 区分 Allowed、Reason、Error，便于 UI 解释拒绝原因；但是错误是否拒绝取决于调用路径，接口类型本身不保证。
3. NewDefaultClient 在非 Docker Desktop 环境返回 NoopClient；在 Desktop feature flag 查询失败或未启用时也返回 NoopClient。该实现是产品部署选择，明显不同于公司未知项 deny。

```81:86:pkg/policy/policy.go
// NoopClient always allows.
type NoopClient struct{}

// Evaluate always returns an allowed decision.
func (NoopClient) Evaluate(_ context.Context, _ Request) (Decision, error) {
	return Decision{Allowed: true}, nil
```

NoopClient 的 EvaluateBatch 同样给每个请求 Allowed:true；SubmitAudit 直接返回 nil 不落审计。不能把“审计函数调用成功”看成有审计记录。

## 实现证据与失败路径

- `policy.go:10-60`：动作、目标和请求身份。
- `:62-79`：决定结构与客户端协议。
- `:81-101`：Noop 的允许/忽略审计行为。
- `:104-116`：环境和 feature flag 分支。

特性服务不可用时走 Noop，与公司“治理不可用则拒绝”的要求相反。公司若使用该 gateway，必须把自己的策略置于不可绕过的执行入口；也可以只取目录和协议机制，不依赖其默认治理客户端。

## 对公司工程的影响

- `contracts/policy.json` 的 fail_closed 必须由 Python 执行层实际执行，不能由网关许可代替。
- `contracts/providers.json` 记录受管 server/端点，远程 catalog 更新不能静默改变信任。
- `packages/` 仍只转调 company-agent invoke，不另起网关工具循环。
- 设备审批保持 mandatory ask；平台密钥只在服务端托管，不进入工具结果。
- 增加反例：治理服务不可用、Desktop feature flag 关闭、未知 transport、审计 sink 不可用。

## 许可与测试范围

根 LICENSE 为 MIT（需与所用依赖和 Desktop 商业服务单独区分）。`pkg/policy/policy_test.go:12-19` 调用 `WithNoDockerDesktop` 后断言返回 `NoopClient`，直接支持非 Desktop 默认允许的分析；本次只静态阅读，未运行。

本轮未验证 catalog 签名、OAuth refresh、Desktop 管理功能、容器网络边界或整个 gateway 的漏洞状况。结论仅针对已读的策略客户端与默认值。

## 取舍

可借 Request 的来源/transport 维度、装载与调用两阶段策略、显式审计接口。
不采纳 Noop 默认放行作为公司业务治理层。
旧稿“凭据托管+gateway等于全部治理”的结论撤回。
