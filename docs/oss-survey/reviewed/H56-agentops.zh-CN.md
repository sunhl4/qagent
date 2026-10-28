# H56 AgentOps：遥测认证轮换与故障隔离

对象 `AgentOps-AI/agentops`；SHA `f8e907b92dabe47232978023fdcb01e2a7d4b752`，提交2026-06-25T01:25:03-07:00；来源 `/tmp/oss-AgentOps-AI-agentops`。静态复核AuthenticatedOTLPExporter及单测；未发送任何遥测或连接外部服务。根许可按LICENSE。

## 实际导出链

spans → 检查最近认证失败时间 → 动态读取JWT → 过滤用户headers → 临时更新HTTP session headers → 父OTLP exporter → 恢复headers → 返回SpanExportResult。JWT provider失败会记录warning并回退已有JWT；认证失败后60秒内直接FAILURE，避免反复认证冲击。这是观测数据出口的退避，不能类比成量子设备任务重试策略。

```86:95:agentops/sdk/exporters.py
        PROTECTED_HEADERS = {
            "authorization",
            "content-type",
            "user-agent",
            "x-api-key",
            "api-key",
            "bearer",
            "x-auth-token",
            "x-session-token",
        }
```

headers大小写归一后过滤，动态Authorization最后写入。锁保护失败时间等局部状态，但session headers临时修改区域不整体在锁内；仅凭此类代码不能宣称并发导出绝无竞争，需结合父类调用及并发测试。普通异常被转为导出失败，日志包含异常文本，部署中还需避免异常串泄漏敏感信息。

## 测试证据

`tests/unit/sdk/test_exporters.py:61-136`mock父export方法，覆盖成功、JWT过期、服务错误、网络错误和异常返回/日志。mock不等于真实HTTP 401/403行为证明，父类可能返回FAILURE而不是抛HTTPError；是否触发本地退避需额外集成测试。本轮未执行。

## 公司取舍

借鉴动态凭据解析、受保护headers、明确导出失败和退避；优先公司已有内网OTel设施，不为调研项目数增加外部SaaS依赖。遥测失败如何影响执行须分阶段：高风险提交前必需的持久审计不可写则拒绝；执行后遥测失败不能据此自动重投，平台受理不确定保持unknown并对账。

导出前只保留允许字段；密钥、科学全文和内部算法正文不进入span属性。遥测身份与企业用户身份分开，SDK token不能当云/HPC授权。该源码不提供公司审计账本、资源申请或计费系统。

证据范围：`agentops/sdk/exporters.py:47-78,80-103,105-120,122-176`；`tests/unit/sdk/test_exporters.py:61-136`；根LICENSE。本轮没有验证服务可用性或完整SDK自动采集范围。
