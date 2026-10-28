# H29 microsandbox：网络模型、引擎与默认值区分

项目 `microsandbox/microsandbox`；SHA `04f924d0b5e146bb83d4ce85041dac46c481dd02`，提交2026-10-21T19:35:20-04:00；来源 `/tmp/oss-microsandbox-microsandbox`。静态Rust模型与测试阅读，未运行VM、代理或WSL内核验证。

## 调用链与范围

network crate总是提供SDK配置模型，只有engine feature加入packet处理、DNS、代理、TLS interception和策略执行。因此依赖模型包不等于已启动网络强制边界。
NetworkPolicy保存有序rule和分方向default；运行时engine按方向first-match-wins解析目的地址/域名索引，secret代理在出站流量中处理占位符与违规行为。

## 三个关键语义

1. serde默认egress/ingress均Deny，是部分JSON缺字段时的处理；profile构造会显式将ingress改Allow。不能笼统说所有配置都双向deny。
2. 同一destination字段在egress看目标、ingress看来访peer；ports始终指guest侧端口。把两者混用可能生成完全不同网络策略。
3. profile Public/Private/Host映射普通规则，空protocol/ports表示any。公司需把默认值、顺序与域解析一起验，不只挑一个allow字段。

```50:58:crates/network/lib/model/policy/types.rs
    #[serde(default = "Action::deny")]
    pub default_egress: Action,

    /// Default action for ingress traffic not matching any rule. The
    /// per-field serde default is `Deny` so partially-specified JSON
    /// fails closed; profile policies built by [`NetworkPolicy::from_profiles`]
    /// flip this back to `Allow` explicitly.
    #[serde(default = "Action::deny")]
    pub default_ingress: Action,
```

## 测试证据

`crates/network/tests/secret_deny_response.rs:1-30`在engine feature下测试Block/BlockAndLog/BlockAndTerminate；`:31-125`构造HTTP已开始响应、分块body、split placeholder、malformed authority等场景，判断何时可安全返回HTTP拒绝、何时必须断开。
这比只看secret.allowed_host字段更深入，但本轮未运行，不能保证当前宿主代理已经正确部署。

## 公司落点

- S4合同若新增网络配置，明示默认动作、规则优先级、入出方向与凭据作用域。
- 不把沙箱网络允许当量子执行授权；设备仍lab/sign ask、boot/algo deny。
- 测试包括部分配置、profile展开、代理未启engine、DNS变化、HTTP响应后再发现secret和WSL功能缺失。
- 工具结果禁止回传secret代理原始日志或完整校准正文。

许可根LICENSE及子crate声明需按固定原文登记，不用“Rust+microVM”推断合规或安全。借机制可以，旧稿“即抄即用”的部署结论撤回。
证据：lib/lib.rs:1-26；model/policy/mod.rs:1-20；types.rs:1-20,39-81,95-122；tests/secret_deny_response.rs:1-125。
