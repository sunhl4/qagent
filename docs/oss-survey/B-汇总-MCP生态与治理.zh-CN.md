# B 册更新：MCP 协议与治理

旧稿“fastmcp 中间件已经足够完整治理”的结论撤回。MCP（Model Context Protocol）框架提供协议、发现、认证与处理扩展点；公司身份权限、设备审批、严格信封、结果限制和外部作业对账仍需要自身合同与实际验证。

请阅读 [逐项目复核索引](reviewed/README.zh-CN.md) 中 16 FastMCP、17 Python SDK、18 TypeScript SDK、19 参考服务器、20 Inspector、21 mcp-scan、22 GitHub MCP、23 Docker MCP Gateway、24/25 Qiskit MCP。

## 对公司的边界

- server 目录和工具列表不能自动扩大生产信任；装配变更须版本化和审查。
- MCP 工具注解、schema 与资源说明不是授权证明；执行期仍穿过公司合同。
- 扫描工具可能访问外部分析服务，必须核对真实数据流，不能默认无出网。
- Qiskit 作业 ID、普通沙箱 ID 不扩张公司三句柄集合；量子软件仍通过平台 provider 调用。
- 协议 SDK 可作为候选依赖，升级要测试协商、取消、错误/结果 schema 和工具列表变化；不再以 `alpha` 标签或 README 推断生产适用性。

关联：[纠错记录](02-纠错记录.zh-CN.md)、[总报告](05-复核总报告.zh-CN.md)。
