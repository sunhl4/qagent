# H03 Goose：批准存储、参数关联与撤销测试

项目 `block/goose`；SHA `5be3f8d3db9a2c4dfd5162bc50c3a35c648b7706`；提交2026-10-22T00:17:41+00:00；来源 `/tmp/oss-block-goose`。静态源码/测试阅读，未运行 Rust 测试。许可根 LICENSE。

## 实现链

`ToolPermissionStore` 用工具名和上下文哈希建立键，记录 allowed、可读上下文、timestamp、expiry。load 从JSON读取并清理过期记录，check_permission 查最后一个未过期记录，save 用临时文件+rename替换。

## 机制分析

1. 哈希绑定参数比仅按工具名记住“允许”更细，但仍未证明用户/租户/参数规范化都满足公司要求；readable_context可能包含敏感输入，不能直接进入公司审计。
2. load对不存在文件返回空store，损坏JSON走错误。原子rename保证文件替换完整性，不等同多个writer一致性或审计不可篡改。
3. 同仓 PermissionManager 测试专门验证 stale manager 不能恢复已撤销权限；不要把该管理器和ToolPermissionStore两个存储层混成一段保证。

```16:19:crates/goose/src/permission/permission_store.rs
    #[serde(skip_serializing_if = "Option::is_none")] // Don't serialize if None
    readable_context: Option<String>,
    timestamp: i64,
    expiry: Option<i64>, // Optional expiry timestamp
```

## 测试证据

`crates/goose/tests/permission_persistence.rs:5-29` 创建当前和陈旧manager，撤销dangerous_tool后陈旧实例写别的工具，断言旧授权未复活。
`:31-47` 验证跨实例持久化；`:49-78` 通过inode变化证明替换而非原地写。该测试范围不证明完整策略引擎免疫所有竞态。

## 公司适用

批准范围摘要、失效时间和撤销反例可借，但设备仍逐次ask，不能因永久允许记录免审。
`contracts/policy.json` 不放宽；`tests/test_dsh_lifecycle.py` 可加入批准过期/撤销/陈旧会话反例。
`diagnostics.py` 保持短白名单，不记录raw readable_context。未知结果以平台查询为准，不把本地permission store当作业账本。

## 范围

本篇精读permission_store及持久化反例，不审Goose全部mode、LLM judge与extension。旧稿笼统安全对比和云扫描推断以此范围收缩。
证据：`permission_store.rs:11-28,45-76,79-109`、`permission_persistence.rs:5-78`、根LICENSE。
