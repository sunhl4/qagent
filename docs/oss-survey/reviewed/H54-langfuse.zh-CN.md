# H54 Langfuse：项目隔离、业务会话与登录会话

对象 `langfuse/langfuse`；SHA `b914c2a58139bbae930af1e3aa4019883588014f`，提交2026-10-21T22:24:26+00:00；来源 `/tmp/oss-langfuse-langfuse`。静态复核Prisma/ClickHouse结构和OTel租户隔离测试；未部署数据库。根许可及enterprise范围需按LICENSE分别判断。

## 数据链与纠错

SDK/OTel上传 → API key关联project → ingestion队列 → ClickHouse observation → 项目限定查询/评分。Prisma的`Session`是登录会话，而`TraceSession`才是业务追踪会话；旧稿将二者混同，必须纠正。TraceSession复合主键包含projectId，不代表仅凭表结构就证明所有API已防越权。

```595:608:packages/shared/prisma/schema.prisma
model TraceSession {
  id          String   @default(cuid())
  createdAt   DateTime @default(now()) @map("created_at")
  updatedAt   DateTime @default(now()) @updatedAt @map("updated_at")
  projectId   String   @map("project_id")
  project     Project  @relation(fields: [projectId], references: [id], onDelete: Cascade)
  bookmarked  Boolean  @default(false)
  public      Boolean  @default(false)
  environment String   @default("default")

  @@id([id, projectId])
  @@index([projectId, createdAt(sort: Desc)])
  @@map("trace_sessions")
}
```

observations包含project、parent、输入输出、成本及时间，使用ReplacingMergeTree和删除字段；这不是不可变审计账本。替换、异步合并、重复写入和最终读取语义都需考虑，不能因“有trace”就声称具备合规审计或财务账单完整性。

## 测试证据

`web/src/__e2e__/otel-tenant-isolation.servertest.ts:20-114`建两个project，以A的key上传span，断言A读到1条、B为0。测试还因队列重试用去重查询避免计数膨胀，说明遥测至少需要考虑重复；不意味着设备执行可以同样重试。本轮未运行，该测试需要完整服务和数据库。

## 公司适配

适合模型/工具性能追踪、评测分数与受控调试，不代替公司统一身份系统或平台作业真相。优先确定哪些允许字段从`diagnostics.py`导出，再通过内网collector接入；不默认上传完整prompt、工具结果或科学数据。

project/key的绑定由宿主提供，不能让模型指定租户。任务关联只用受控标识；内部算法实现、密钥、QASM及设备原始结果留平台。持久化审批审计需要独立完整性、保留和访问策略，现有stderr诊断与Langfuse追踪均不可直接标为已满足。

证据范围：`packages/shared/prisma/schema.prisma:44-51,595-608,610-628`；`packages/shared/clickhouse/migrations/canonical/0002_observations.up.sql:1-46`；上述隔离测试`:20-114`；根LICENSE。范围限于结构与一条ingestion隔离证据。
