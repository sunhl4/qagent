# 最近三天对话与工作挂载(2026-10-26 ~ 2026-10-28)

> 目的:把近三天的对话脉络与其落地产物挂载到工作区,供后续继续开发时检索。
> 依据:`docs/` 实现留档、`docs/evidence/` 证据、恢复出的对话摘要(`_tmp_ovl_49fee64b.txt`、`_tmp_ovl_b015c964.txt`、`_tmp_chat_transcript.txt`)、本会话记录。
> 对话 ID 索引见文末。

---

## 2026-10-28(今天)

### 会话 A:Overleaf Git 桥接主线 + 验收链(进行中,最后写入 12:44)
主线延续 `b015c964`,今天上午 10:32-11:28 与下午 12:03-12:44 两段都在推进:

| 时间 | 变更 |
| --- | --- |
| 上午 10:32-11:28 | office 插件落地:`src/company_agent/office_create.py`、`office_ingest.py`、`audit_chain.py`、`workspace_files.py`;packages/company-agent-office;profiles 的 office 依赖;preset/tools 合同更新(工具数 58→59);对应测试(test_office_create / test_office_ingest / test_audit_chain / test_workspace_files) |
| 下午 12:03-12:15 | 全量测试回归与实现文档:`docs/implementation-2026-10-28-overleaf-git-bridge-probe.zh-CN.md`(12:15);`workspace_files.py` 工作区围栏(12:14,与并行迁移会话协同修复合入) |
| 下午 12:15-12:30 | overleaf e2e 链:`tests/test_overleaf_e2e.py`(12:27)、`test_plan_hub.py`、`plan_hub.py`、`test_manual_evidence.py`、`verify_manual_evidence.py`、`test_evidence_boundaries.py` |
| 下午 12:33-12:44 | 部署探针与验收链:`_probe_bridge_server.py`(git 桥回环探针)、`_probe_e2e_chain.py`(新)、`acceptance_pytest.py`、`verify_acceptance.py`、`verify_dsh_profiles.py`、`pyproject.toml`(12:36) |

### 会话 B:WSL 迁移与全量验证(本会话,10:06-12:33)
- 把工程完整迁移到 `\\wsl$/…/home/sunhl/qagent-copy`(ext4),构建校验过的同步管道(base64 + SHA-256 清单 + 接收端逐文件核对)。
- 完整测试套件:**1114 通过 / 2 失败 / 1 跳过**;compliance gate **25/25 绿**。
- 修复真实 Bug:`src/company_agent/workspace_files.py` 的 `resolve()` 在 POSIX 补上 `_reject_link_components`(中间目录符号链接防护),双端(W:D:)同步加入,`test_cloud` 边界测试两边都绿。
- 发现 D: 在途缺口:`profiles/company-agent/pnpm-lock.yaml` 未纳入 office 依赖,`bootstrap_dsh.sh` 的 `--frozen-lockfile` 失败 → 两个在途用例挂起(rerun 待锁文件再生)。
- 双端卫生清理:根目录同步工具、`build/`、`unitqc_company_agent.egg-info` 等已清;`tests/ui/node_modules`、`profiles/*/node_modules` 符号链接树已重建验证。

---

## 2026-10-27

- **审计证据**:`docs/evidence/compliance-local.json`(21:07)。
- **Overleaf 主链全绿**:b015c964 会话产出(`docs/implementation-2026-10-28-overleaf-git-bridge-probe.zh-CN.md` 内回忆 67+ 测试全绿,push 永不删远端文件等 fail-closed 断言)。
- **49fee64b 会话**(大量 msgs):检索并恢复 Overleaf/LaTeX 相关被删文件——恢复件存于 `_recovered_backup`(`invoke.py`、`latex_workspace.py`、`overleaf_sync.py`、`policy.py`、`test_overleaf_sync.py`)。
- **42ae864b / 6c70da78 会话**:检索 WPS 全家桶 / mework / 思维导图的调研文档(`_tmp_chat_transcript.txt`)。

---

## 2026-10-26

晚上 20:46 批量落档(一次成型):
- **架构评审**:`quantum-agent-architecture-review-2026-10-20.zh-CN.md`、`quantum-agent-workspace-customization-audit-2026-10-22.zh-CN.md`、`quantum-agent-workspace-plan-v0.3.zh-CN.md`、`quantum-agent-delivery-estimate-2026-10-20(.zh-CN.md/.json)`。
- **治理与合规(P8)**:`company-agent-plan-p8a1-governance-boundary-2026-10-26`、`p8a2-license-audit`、`p8a3-license-tree-audit`;`docs/licenses-register.json`(21:29)。
- **交付与规划**:`company-agent-2000-person-days-development-plan-v1.0(.json/.zh-CN.md)`(22:00)、`company-agent-harness-framework-v0.8`。
- **Overleaf 混合架构**:`implementation-2026-10-26-overleaf-hybrid-architecture`;同期还有 access-seam / plan-hub / portal-bridge / ui-receipt-contract / latex-runtime-sync 等实现留档,`docs/evidence/portal-bridge-2026-10-26.json`、`latex-matrix/2026-10-26-local-matrix.json`、`ts1-recert/recertification.json`。
- **OSS 调研 57 篇**:`docs/oss-survey/**`(A~G 分组与 reviewed 目录,含 evidence 三包与校验脚本)。

---

## 对话 ID 索引(agent-transcripts 存根 + 恢复摘要中出现)

| 对话/会话 | 内容 | 状态 |
| --- | --- | --- |
| `b015c964-0c2a-4b87-80c2-959f5cacebf3` | Overleaf Git 桥接主线(读公司教程→合同/适配器/插件/审计) | 已落地,见 10-28 实现文档 |
| `49fee64b-643b-49cb-a56d-398b5f41a0ad` | 历史检索与被删文件恢复(overleaf/latex 链) | 恢复件在 `_recovered_backup` |
| `6c70da78-cf62-4db9-87b7-430a686c19a1` | WPS 全家桶 / mework / 思维导图文献检索 | 摘要在 `_tmp_chat_transcript.txt` |
| `5a8907e3-3331-4f08-bdd0-7c3bcaa463bf` | 更早的 overleaf 讨论记录(仅 jsonl 存根) | 存根 1 字节 |
| `f3fcac59-fb33-4b0e-9873-18640227a367`、`ecc65ac5-fa44-4c73-8d05-60c11fc25675` | 今日迁移/验证与 office 链会话 | 本会话与并行会话进行中 |
> 说明:工作区 `agent-transcripts/` 仅存 1 字节存根,完整消息仍在 Cursor 应用存储;此文档以 docs 留档 + 恢复摘要为为准。

---

### 会话 C:WSL 副本晚间接力(22:02-22:44)
- 晚间快照同步(551 文件,含 docs;逐字节校验 0 偏差)→ profiles/runtime 安装 + `bootstrap_dsh.sh` rc=0(D: 端锁文件已含 office 后解锁)。
- 修复跨平台 Bug:`src/company_agent/office_open.py` 模块级 `_startfile = os.startfile` 在 POSIX 导入即炸,波及整条 invoke 链(cmd/verify_dsh_profiles/overleaf_e2e 收集失败)→ 改为 `getattr(os, "startfile", None)` + `_shell_open` fail-closed 报错;双端同步(sha `ef3015fb…`)。
- 全量套件:**1173 通过 / 10 失败 / 3 跳过**。10 个失败全部属于并行会话合同批次 3(office pptx/审计切片,contracts 21:57)自身开发顺序的"测试同步"阶段:test_office_convert ×2、test_office_open ×4(WPS 注册表分支 fixture 属 Windows 侧)、test_cli ×2 / test_installed_wheel / test_verify_dsh_profiles 的工具计数门。overleaf_e2e 离线用例经 startfile 补丁后转绿。
- 证据:compliance gate **25/25 绿**;license tree scan 86 包(office/UI 并入后)无违禁族。

---

## 下一步(挂接点)
1. 等 D: 上 overleaf/验收链会话(最后写入 12:44)稳定后取新快照同步 copy。
2. copy 端再生两份 profile 的 pnpm-lock(纳入 office 依赖)→ 重跑 `bootstrap_dsh.sh` → 复测 `test_acceptance` / `test_verify_dsh_profiles` 的 2 个在途用例。
3. 与 D: 端共享再生后的 lockfile(经校验管道),让 D: bootstrap 同步解锁。
4. 继续下午主线:overleaf git 桥 e2e 链与部署探针的验收闭环。
