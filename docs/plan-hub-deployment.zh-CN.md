# 计划中枢与 LaTeX 协作区部署 runbook（GitLab CE + Overleaf CE）

日期：2026-10-26  
适用：GitLab CE 与 Overleaf CE 的 IT 侧上线动作。决策保留在本 runbook：GitLab 是计划和版本权威，Overleaf CE 只做可信内网的排版协作，阶段结束用 ZIP 快照归档回 GitLab；不把 Overleaf 网页放进中栏，不假设社区版有 Git bridge。编译门禁见 [LaTeX 阶段 0](latex-lab-phase0.zh-CN.md)。
Agent 侧代码件已就绪（`company.plan` 9 工具 + `company.latex` 11 工具）；本文件只覆盖服务器与运行时接线。

## 一、GitLab CE（计划/审批中枢）

1. 内网主机（8C/16G 起，磁盘按项目数估 20G+），Docker 安装 omnibus：

```bash
docker run -d --hostname gitlab.<内网域名> --name gitlab \
  --shm-size 256m -p 443:443 -p 80:80 \
  -v /srv/gitlab/config:/etc/gitlab -v /srv/gitlab/logs:/var/log/gitlab \
  -v /srv/gitlab/data:/var/gitlab/data gitlab/gitlab-ce:latest
```

2. 反代 + HTTPS（公司证书），只在内网/VPN 可达，禁公网暴露。
3. 备份：`root` crontab 每日执行 `gitlab-backup create`（保留 ≥14 天，异地同步一份），
   并演练一次恢复；`/etc/gitlab/gitlab-secrets.json` 单独备份（没有它备份不可恢复）。
4. 服务账号：`company-agent`（最低权限 API），生成 PAT（设到期），仅授予 allowlist 内项目的
   `read_api` + 项目级写权限（Issue/MR/评论/里程碑）。
5. Agent 允许清单：插件读取 `COMPANY_AGENT_GITLAB_PROJECT_ALLOWLIST`（逗号分隔
   `group/project`，≤16 条）；增删名单由组长在 GitLab 记录变更。

## 二、Overleaf CE（实时 LaTeX 协作区）

1. 按 [Overleaf Toolkit](https://github.com/overleaf/toolkit) 快速上手部署（`bin/init`、`bin/up`）；
   sharelatex 数据目录 + mongo + redis 纳入同一备份策略。
2. 仅对内网可信员工开放（社区版无 Server Pro 的编译沙箱；官方明确要求所有用户互信的环境）。
3. 上传入口限 ZIP 导入导出；不要把 Overleaf 当 Git 权威（Git bridge 是 Server Pro 功能，社区版没有）。

## 三、Agent 运行时接线

在 DSH 启动环境（开发机 `~/.cache/unitqc-company-agent/runtime-dev.env`；生产由部署系统注入）加：

```bash
COMPANY_AGENT_GITLAB_URL=https://gitlab.<内网域名>
COMPANY_AGENT_GITLAB_TOKEN=<服务账号PAT>          # 仅环境注入，禁止写入仓库或合同
COMPANY_AGENT_GITLAB_PROJECT_ALLOWLIST=team-a/report,group-b/plan
```

校验（逐层）：

```bash
# 1) 合同目录里确认 9 个 plan 工具
COMPANY_AGENT_CONTRACTS_DIR=$PWD/contracts PYTHONPATH=src python3 -m company_agent.cli tools | head

# 2) fail-closed 自检：清掉 URL 后调用必须诚实报 "not configured"，不允许伪成功
env -u COMPANY_AGENT_GITLAB_URL python3 -m company_agent.cli invoke \
  --tool company_plan_projects --preset lab --args '{}'

# 3) 只读真实连通（lab 允许）：应返回项目行与 allowlisted 标志
python3 -m company_agent.cli invoke --tool company_plan_projects --preset lab --args '{}'

# 4) 写路径：lab 下先 needs_ask，人工批准后成功（DSH 会话内触发审批条）
python3 -m company_agent.cli invoke --tool company_plan_note_create --preset lab \
  --args '{"target":"issue","project":"team-a/report","iid":N,"body":"..."}'
```

行为约定（合同层已固化）：未配置→诚实失败；allowlist 外项目读/写均拒；401/403 →"凭据需人工处理"；
结果不回显令牌与 URL；lab 写入全部留 `ask` 审批记录。

## 四、上线检查单

- [ ] GitLab HTTPS + 备份 + 恢复演练通过；PAT 最小权限并设到期
- [ ] Overleaf CE 可编辑/编译/导出 ZIP；备份可恢复
- [ ] 三个环境变量注入 DSH 运行时；`company_plan_projects` 返回 allowlisted 清单
- [ ] 一次建任务（ask 批准）→ 一次评论 → 一次里程碑挂接 → 一次关闭 全链路演练
- [ ] `skills/company-plan` 已随 lab 会话挂载（DSH 会话左侧技能面板可见）
- [ ] 首周结束由 Agent 输出周报草稿回 MR/Issue，组长确认流程闭环

## 五、边界与提醒

- 编译沙箱（Sandboxed Compiles）、LDAP/SAML SSO、Git bridge、评论与修订跟踪属 Server Pro 功能；
  社区版默认按"可信内网工作组"使用，涉外部协作另行评审。
- Agent 不做删除类操作（删项目/删 Issue/删分支）；此类动作一律由人工在 GitLab 执行。
- tokens 只经环境注入；发现泄露立即在 GitLab 撤销 PAT 并换发（无需改代码）。
