# Overleaf 需求的混合架构决策（GitLab CE + Overleaf CE + Agent）

日期：2026-10-26  
状态：决策记录（对应另一对话窗口中"公司想用 Overleaf 但不购买订阅，希望在 Agent 内完成"的方案）。  
该方案第一半（LaTeX 文档工作区）由 `company.latex` 批次落地（见 [latex-lab-phase0](latex-lab-phase0.zh-CN.md)）；
第二半（计划/审批中枢）由 `company.plan` 批次落地（见 [implementation-2026-10-26-plan-hub](implementation-2026-10-26-plan-hub.zh-CN.md)）。

## 一、需求还原

- 不购买 Overleaf 云订阅；
- 文档要能被组员/组长同时或快速看到修改；
- 计划管理需要在 Agent 内完成；
- 遵循公司规则：DSH 是唯一运行时，工具走合同，写工具人审。

## 二、结论

1. **计划与审批中枢**：自托管 GitLab Community Edition（Issues/MR/里程碑/评论/CI 产物），Agent 通过 `company.plan` 读任务、经人审建 Issue/评论。
2. **实时 LaTeX 协作**：自托管 Overleaf Community Edition，仅向可信内网用户开放；`company.latex` 本地工作区承担 Agent 侧草稿与本地编译。
3. **同步方向单向**：GitLab 是计划/版本权威；Overleaf 是排版协作区；阶段结束时用快照（ZIP/git bundle）归档回 GitLab，不做双向实时同步。
4. **不做的事**：不把 Overleaf 网页塞进中栏；不给 Agent 无限 Shell/桌面控制；不在社区版上假设有 Server Pro 的 Git bridge/评论/SSO/沙箱编译。

## 三、Overleaf CE 与 Server Pro 的差距（官方文档 2026-10 版本核对）

| 项 | Overleaf CE | Server Pro |
| --- | --- | --- |
| 实时多人编辑 / 项目历史 | 有 | 有 |
| 评论 / 实时跟踪修订 | 无（官方对比表 X） | 有 |
| Git integration（git-bridge） | 无（Server Pro 专属配置） | 有 |
| LDAP/SAML SSO、自动注册 | 无 | 有 |
| Sandboxed Compiles 编译隔离 | 无 → 只能用于"所有用户可信"环境 | 有 |
| 支持 | 社区 GitHub Issues | 商业支持 |

因此：CE 部署在 VPN/内网之后，只给可信员工；涉及外部协作者或审计需求时另行评估 Server Pro 或商业许可。

## 四、GitLab 侧部署要点（IT 侧动作清单）

1. 一台内网主机运行 GitLab CE（Omnibus/Docker 安装）；开启 HTTPS 与每日自动备份，并演练从备份恢复凭据与配置；
2. `COMPANY_AGENT_GITLAB_URL` 指向实例 API 根；`COMPANY_AGENT_GITLAB_TOKEN` 用专用服务账号 PAT（最小权限：仅 read_api 与 allowlist 内项目的 api 写权限）；
3. `COMPANY_AGENT_GITLAB_PROJECT_ALLOWLIST` 固化为项目清单（读过滤 + 写门禁）；
4. Overleaf CE 单独实例，`sharelatex` 数据、mongo、redis 纳入同一备份策略；两者都不暴露公网；
5. 组长在 GitLab 维护 `allowlist` 变更记录（谁被加入项目名单）。

## 五、流程闭环（phase 流程）

```
组长在 GitLab 建项目/里程碑
   → Agent 读取任务（company_plan_issues / issue_get）
   → Agent 起 LaTeX 草稿（company_latex 工作区，本地编译）
   → 组员在 Overleaf CE 实时协作 / Agent 产出快照
   → 通过人审后 Agent 建 Issue/MR 并评论留痕（company_plan_issue_create / note_create，lab 预设 ask）
   → GitLab CI/PDF 产物归档 → Agent 报告进度 → 组长验收
```

写操作一律 `lab` 预设人审；`algo` 只读；`boot`/`sign` 不可见。

## 六、与既有批次的关系

- `company.latex`（11 工具）负责 Workspace 内文档源码与编译；
- `company.plan`（6 工具）负责任务、审阅与留痕；
- 两者共享 `lab` 人审门与 `boot`/`algo` 边界语义，P1 的租户/身份（`identity.subject_source`、enablement）落地后按用户身份过滤项目名单。
