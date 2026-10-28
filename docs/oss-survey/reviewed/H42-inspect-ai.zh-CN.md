# H42 Inspect AI：审批一致性与评测隔离

对象 `UKGovernmentBEIS/inspect_ai`；SHA `c2fc3d9e3ff3fdc389be2933c6e3f9824648876e`，提交2026-10-21T16:41:11-04:00；来源 `/tmp/oss-UKGovernmentBEIS-inspect_ai`。本轮静态复核审批策略、工具预算说明与相关测试；不启动其模型/工具循环。许可以根LICENSE为准。

## 审批实际链

配置或策略列表 → 编译工具匹配模式 → 格式化函数名及参数 → 按顺序调用匹配审批器 → 遇非`escalate`决策返回 → 无审批器或全部升级时拒绝并记录。模式会附加`*`，且匹配的是格式化调用字符串，因此不能简单宣称它与公司的精确工具名策略语义相同。

```75:82:src/inspect_ai/approval/_policy.py
        # if there are no approvers then we reject
        reject = Approval(
            decision="reject",
            explanation=f"No {'approval granted' if has_approver else 'approvers registered'} for tool {call.function}",
        )
        # record and return the rejection
        record_approval("policy", message, call, view, reject)
        return reject
```

配置模型还把未知字段收集进`params`，是该框架的配置扩展机制，不应移植为公司的严格执行信封。`record_approval`提供评测事件，不能仅据函数名推断已满足公司持久化合规审计。

## 预算及测试

`src/inspect_ai/tool/_tool.py:183-192`说明工具并行需显式开启；结果预算以字节计，默认递延到GenerateConfig的16KB，0可关闭截断。公司现有合同是64000字节总量、单字符串4000、列表32、映射64、深度8，不能以此覆盖；完整科学结果必须留平台，禁止静默截断后仍声称完整成功。

`tests/approval/test_approval.py:112-123`核验事件审批器和决策；`:135-177`覆盖批准、拒绝、模式不匹配及升级链。测试采用mock模型与加法工具，是适合公司借鉴的无副作用策略回归方式；本轮未运行上游测试。

## 公司适配

在现有合同测试中增加“策略结果—注册工具可见性—执行前拒绝—审计事件”一致性矩阵，尤其device在lab/sign必须ask、boot/algo必须deny。评测器只在离线测试中使用，不作为DSH之外的第二生产Runtime。

容器隔离与网络规则须逐个sandbox实现检查；一个默认模板的无网络设置不代表自定义Dockerfile同样隔离，也不代表可安全挂载真实云/HPC凭据。设备未知结果只查平台事实，不因评测重跑机制再次提交。

证据范围：`src/inspect_ai/approval/_policy.py:33-60,62-84,102-127`；`src/inspect_ai/tool/_tool.py:183-192`；`tests/approval/test_approval.py:112-177`；根LICENSE。
