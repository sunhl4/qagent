# H32 Open Interpreter：当前Rust/Codex fork与批准动作

对象 `openinterpreter/Open-Interpreter`；SHA `ac1fcc8fe57aba51fcc3c79afd57a0883237fe87`，提交2026-10-11T01:37:07+01:00；来源 `/tmp/oss-openinterpreter-Open-Interpreter`。根LICENSE Apache-2.0。静态复核，不运行安装器或编码工具。

## 对旧稿的直接纠正

README:46-84明确当前为Codex fork、支持harness切换和Codex exec兼容；不是旧Python本地解释器目录，也不能沿用历史AGPL标签。公司仍只把官方Codex作为隔离宿主provider，不因同源兼容放开设备工具。

## 实现链和机制

`codex-rs/core/src/tools/approvals.rs`是批准policy阶段与reviewer路由中心，ApprovalContext包含call_id、tool_name、取消token、理由、网络上下文等；ApprovalAction用serde判别联合表示ExecCommand/WriteStdin等具体动作。

- 批准动作携带environment_id、cwd、sandbox_permissions及additional_permissions，说明批准范围不止一个按钮或命令字符串。
- WriteStdin携带process_id和approval_id，向已存在进程写入也可能有副作用，不是安全“读操作”。
- 行为可走自动review、hook、人工等路径；公司不得采用这些替代mandatory设备ask。

```54:60:codex-rs/core/src/tools/approvals.rs
pub(crate) struct ApprovalContext {
    pub(crate) review_context: GuardianReviewContext,
    pub(crate) cancellation_token: Option<CancellationToken>,
    pub(crate) call_id: String,
    pub(crate) tool_name: ToolName,
    pub(crate) strict_auto_review: bool,
    pub(crate) approval_reason: Option<String>,
```

## 测试

approvals_tests.rs:7-35断言deny网络amendment和MCP policy amendment转拒绝；:38-53验证Abort结束turn；:56-78验证timeout说明来自当前model。
这表明权限结果和错误分类应结构化，不证明公司应相信模型裁判决定安全。测试只阅读未执行。

## 公司落点

批准关联绑定请求、工具、参数、身份和执行环境；runtime.js继续只接受DSH保留上下文。网络授权不是量子作业授权。
测试取消后回包、批准后改cwd/参数、向现有进程写入绕过、模型review与硬deny冲突。
官方Codex仍permissionMode never/inheritsParentContext false，且不暴露模型可见委派工具；此fork不作为替代runtime接入。

证据：README:46-84；approvals.rs:54-92；approvals_tests.rs:7-78；LICENSE:1-24。未审全部fork差异、沙箱后端与供应链，不宣称产品可直接集成。
