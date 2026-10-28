# 公司计划中枢（GitLab CE / company.plan）落地：合同 → 适配器 → DSH 插件 → 测试

日期：2026-10-26  
批次：按[混合架构方案](implementation-2026-10-26-overleaf-hybrid-architecture.zh-CN.md)第二半（计划/审批中枢）执行；
与 [LaTeX 工作区批次](latex-lab-phase0.zh-CN.md)、[P0 记录](company-agent-plan-p0-2026-10-26.zh-CN.md) 互补。
开发顺序符合工程治理：先合同、再 Python adapter、再 DSH 插件、最后测试。

## 一、本批新增能力：`company.plan`（kind `plan`，provider `company-plan`，contract `company.plan/2.0`）

承载"组员↔组长↔Agent"的计划管理闭环（GitLab、Milestone、审批流水）。工具 9 个，全部 fail-closed：

| 工具 | 类型 | 审批 | 输出预算 |
| --- | --- | --- | --- |
| `company_plan_projects` | 读 | allow | ≤24 行（id/path/name/分支/可见性），`allowlisted` 标志 |
| `company_plan_issues` | 读 | allow | ≤24 行（iid/标题/状态/标签/人数/更新时间），`complete` 标志 |
| `company_plan_issue_get` | 读 | allow | 单条 + 描述截断 4000 字节 + 评论数 |
| `company_plan_issue_create` | 写 | ask（lab；algo/boot/sign 见下） | 返回 iid，不带正文 |
| `company_plan_issue_write` | 写 | ask（lab） | 改标题/描述/close/reopen/标签/挂里程碑（PUT 局部更新，至少一个字段），返回有界摘要 |
| `company_plan_mrs` | 读 | allow | ≤24 行（iid/标题/状态/分支/draft/sha） |
| `company_plan_milestones` | 读 | allow | ≤24 行（id/标题/active/closed、起止日期 YYYY-MM-DD） |
| `company_plan_milestone_create` | 写 | ask（lab） | 创建里程碑（标题+可选起止日），返回 id |
| `company_plan_note_create` | 写 | ask | 返回 note_id（issue 或 MR 评论） |

前端语义：组员看任务并投稿，Agent 生成草稿/周报正文并经人审提交，组长审阅 MR 与评论留痕；
里程碑由组长人审建立，Agent 读取排期并把任务挂上里程碑；归档完成后 Agent 收口任务（关闭/打标签）。

## 二、合同层改动

- `contracts/capabilities.json`：新增 `company.plan`（approval=human，无 handles；7 工具批 + 里程碑批 = 9 工具）。
- `contracts/tools.json`：9 个工具 schema（含 `issue_write` 的可选 `milestone_id`；输入输出全部 `additionalProperties: false`、行数/字节上限、`plan` 类型枚举加入 `company_capabilities` 的 kind 枚举）。
- `contracts/presets.json`：`lab`=50（+9 全量）、`algo`=29（读含 milestones）、`boot`/`sign` 只含并行批次的受控工具；
- `contracts/policy.json`：`plan_write_tools`（4 个写工具）、`plan_write_provider=company-plan`、ask=`lab/sign`、deny=`boot/algo`。

## 三、内核（Python adapter）

- 新增 `src/company_agent/plan_hub.py`：有界 GitLab REST v4 客户端。
  - 环境变量：`COMPANY_AGENT_GITLAB_URL`（仅 http 环回/https 任意、无 query/fragment/userinfo、规范化校验）、
    `COMPANY_AGENT_GITLAB_TOKEN`（必配，`PRIVATE-TOKEN` 头）、
    `COMPANY_AGENT_GITLAB_PROJECT_ALLOWLIST`（可选 ≤16 个 `path_with_namespace`，配置后读过滤、写硬门禁）。
  - 失败语义：401/403→"rejected authentication"；404→"not available"；5xx→"service error"；传输→"unreachable"；
    全部为通用短语，绝不回显 URL。响应 ≤1,000,000 字节、20s 超时、JSON-only、禁止重定向、禁止代理。
  - 内容红线：凭据回显禁止（`COMPANY_AGENT_GITLAB_TOKEN` 已加入 `sanitize` 已知凭据名）；字段级截断先于合同校验。
- `invoke.py`：6 个工具注册进 `_LOCAL_TOOLS`；`provider_state` 的 local 集合加入 `plan`。
- `catalog.py`：canonical 工具名单 +6、`expected_providers` 加 `company.plan→company-plan`、`load_policy` 期望字段集合 +4。
- `policy.py`：plan 写分支（镜像 latex 写分支的校验与 ask/deny 语义）。
- `capabilities.py`：期望 kind 映射与能力集合加 `company.plan`。

## 四、DSH 插件层

- 新建 `packages/company-agent-plan/`（`package.json` + `src/index.js`）：只注册 `["company.plan"]`，可见性完全交给 preset 目录。
- `packages/company-agent-policy/src/index.js`：`ASK_ROUTED_TOOLS` 加 4 个写工具；审批理由模板逐工具给出有界理由（project/title/target/iid/fields/due）。
- profiles：两个 profile 的 `cordis.patch.yml` insert 列表加 `company-agent-plan`（均置于 `company-agent-latex` 之后）、
  两份 `package.json` 加 file: 依赖、`corepack pnpm install --offline` 更新两份 lockfile 与 node_modules。
- Skill 注册：`skills/company-plan/SKILL.md`（工具选择、ask 语义、allowlist/凭据边界、与 LaTeX 工作区联动与文档公式规则），
  `contracts/skills.json` 登记 `sha256` 钉；`when` 限定 company-agent profile 的 `lab`（minimal 不挂载）；
  `test_skills_registry` 的 lab 同步钉与 `test_dsh_profiles` 的 frontmatter 名单已同步。

## 五、测试与门禁（本批实测）

- 新增 `tests/test_plan_hub.py`（26 用例，全部环回假 GitLab，无真实出网）：
  合同接线、preset 矩阵（lab 全量 / algo 只读 / boot+sign 无）、写工具 needs_ask→approved 流、
  未配置诚实失败、allowlist 过滤+写门禁+畸形拒绝、行映射、HTTP 状态映射泛化、凭据回显拒绝、
  参数验证 fail-closed、`issue_write` PUT 局部更新与空更新拒绝、里程碑排期映射与创建。
- 计数钉同步：`test_installed_wheel` 40→50 / 10→11、`test_cli` 50+`company_plan_milestone_create`、
  `test_plugin_runtime` 50+last-name、`test_verify_dsh_profiles` company-agent 探针 48→58
  （lab 50 + managed builtins 7 + skill 1）、`test_no_legacy` 包名白名单加 `company-agent-plan`/
  合同清单加 `tenants.json`、`test_receipts` lab 审批清单含 4 个 plan 写工具、
  `test_contracts` 注册矩阵加 plan 插件。
- 全量默认范围 pytest：**943 passed / 2 deselected / 0 失败**（latex_toolchain 与 platform_compatibility 仍 opt-in）。
- `scripts/compliance_gate.py`：**ok（17 项）**、`scripts/verify_dsh_profiles.py` 实测全部会话按合同精确组装
  并拒绝非法组合、检索基准通过。

## 六、诚实边界与后续

- GitLab CE/Overleaf CE 的服务器部署步骤与上线检查单见
  [部署 runbook](plan-hub-deployment.zh-CN.md)（IT 侧动作；本机环境无 Docker，
  adapter 在端点未配置时全部诚实报错，不会伪成功）。
- `latex push→issue 附 PDF` 联动属后续批次（`company_latex_push/pull` 归 LaTeX 批次管辖）。
- 并行批次接缝：公司 `company_fetch`（boot/algo）由另一会话落地并自带门禁；其根目录试验产物本轮已由该会话清理，
  相关计数钉由该会话按当前事实收敛（本批不改判、不对并行文件的钉做重复改写）。
- 关联事实：工具 50 / 能力 11 / skill 5 / lab 探针 58；全量默认范围 pytest **943 通过/2 排除/0 失败**；
  合规门禁 **18 项 ok**；DSH 实测与基准通过。
