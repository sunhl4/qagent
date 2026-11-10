---
name: company-plan
description: 管理公司计划与文档流程：读任务、经人审建任务/评论/挂里程碑，与 LaTeX 工作区联动归档收口。
---

# 公司计划与文档流程

本 skill 约束 `company.plan` 工具组（GitLab 计划中枢）的用法。所有读操作在配置了 allowlist 后按名单过滤，
写操作在 `company_grant_open` 覆盖的次数用尽前沿用那一张卡；次数用尽、授权过期或另一条会话时重新询问。algo 只读，boot 拒绝这些写操作。

## 工具选择

1. 排期先行：`company_plan_projects`（项目清单与 allowlist 状态）与 `company_plan_milestones`（里程碑与起止日期）；
   不要凭记忆编造项目路径或里程碑，以返回行内的 `path` / `id` 为准。
2. 任务上下文：`company_plan_issues` 列任务（默认 opened），`company_plan_issue_get` 取单条细节
   （描述已截 4000 字节，需要完整内容时向组长索取，不要反复拉取）。
3. 写动作四件套（均需 ask 批准）：
   - `company_plan_issue_create` 建任务：标题 ≤255 字、描述 ≤4000 字节，只描述事实与验收标准；
   - `company_plan_note_create` 评论留痕：target 选 issue 或 merge_request，正文 ≤4000 字节；
   - `company_plan_issue_write` 收口：close/reopen、改标签或把任务挂上里程碑（`milestone_id` 用 milestones 返回的 id）；
   - `company_plan_milestone_create` 建里程碑：先经组长确认排期，再创建。
4. 审阅上下文：`company_plan_mrs` 读 MR 状态（分支/draft/sha），不要试图通过它读 diff 或仓库正文。

## 边界

- 未配置 GitLab 端点/凭据时工具会诚实报错（"not configured"），此时如实转告网络管理员，
  不要虚构任务数据，也不要改用任意网络抓取工具绕开合同。
- allowlist 拒绝（"outside the configured plan hub allowlist"）意味着项目未获授权：向组长申请，不要重试别的写法。
- HTTP 401/403 表示凭据失效；凭据不允许出现在任何回复里，发现问题只说明"计划中枢凭据/权限需要人工处理"。
- 工具结果里的 iid/milestone_id/note_id 是唯一可回传的标识；不要把内部数据库 id 或长文正文带出计划系统。
- 与 LaTeX 工作区联动：在 `company_latex` 工作区完成草稿与编译后，把定稿说明写入 issue/MR 评论；
  外发光（对外发送）与删除操作必须由人执行，Agent 不做。
- 任务正文遵循文档规则：数学公式行内用 \(...\)，块级用独立行 $$ 并在闭合后空行；表格内禁用裸 `|…|` 基数记号。
