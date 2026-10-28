# H31 container-use：单租户内存状态不等于企业隔离

项目 `dagger/container-use`；SHA `2e43e625e95216b719ec9338f4034fd3a0be2734`，提交2026-08-12T09:30:35-07:00；来源 `/tmp/oss-dagger-container-use`。静态阅读，未启动Dagger/容器；许可根LICENSE。

## 真实链路

single-tenant模式工具可省略environment_id，从进程全局currentEnvironmentID/source读取；setter同锁更新二者。MCP启动/通知时requestRoots向客户端问roots列表，保存后用于repoOpenErrorMessage提示可用仓。

## 三个机制和失败行为

1. 缺current environment直接错误，不随便生成默认环境；但状态只在进程内、不持久，不能用于断线后的业务事实恢复。
2. mutex解决读写并发不代表租户隔离。源码注释明确单进程假设单chat session；若多用户共用需要另设计会话作用域。
3. requestRoots detach cancellation后加30秒timeout，错误记录后吞掉，因为roots是hint不是授权。不能把客户端声明root视为服务端允许root。

```15:20:mcpserver/roots.go
// clientRoots holds the roots provided by the MCP client. Agents frequently
// pass a wrong environment_source; the roots give them a concrete hint about
// which repositories the client actually has open.
//
// This assumes a single client, which may go out the window when we add
// support for streaming http.
```

## 测试

singletenant_test.go:7-54验证setter/getter和更新两个字段；:56-70验证未设环境出错。它们没测试多客户端隔离，也未运行。

## 公司落点

- sandbox/environment ID与科学资源句柄分开，绝不能映射twin_id。
- `profiles/`仍受管，通用代码能力要有服务端身份与路径约束。
- 工作台恢复通过平台查询作业，进程内current状态不能作为已执行证明。
- 测试多会话串用环境、重启后空状态、客户端伪造root、超时后无效hint。

证据：singletenant.go:1-23,25-53；roots.go:15-43,45-73；singletenant_test.go:7-70；LICENSE。可借workspace隔离思路，不引完整执行工具绕过DSH策略。
