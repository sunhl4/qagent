# LaTeX 工作区运行时与远端同步批次（company.latex 收口：11/11）

日期：2026-10-26  
性质：完成 [latex-lab-phase0](latex-lab-phase0.zh-CN.md) 与 [计划中枢批次](implementation-2026-10-26-plan-hub.zh-CN.md) 遗留的
`company.latex` 5 个未实现工具（原为显式 `unconfigured` 桩）。开发顺序：先合同 schema，再 adapter，插件层零改动（注册按目录自动跟随），最后测试。

## 一、本地快照运行时（`latex_workspace.py`）

- `company_latex_checkpoint`：把项目内受管源（tex/bib/cls/sty/bst）快照进
  `.latex-snapshots/chk-<UTC时间戳>-<6hex>/`，快照上限 12 个（超出滚动淘汰），单个文件 ≤2MB、总量 ≤50MB；
  快照目录对 `structure/compile/push` 的枚举一律不可见（`_project_files` 增排除规则）。
- `company_latex_diff`：对最新检查点比较（可选单文件），difflib 行级差异，输出每文件 added/removed
  与首个变更 200 字节预览，行数预算 ≤32 行。
- `company_latex_revert`：从既有检查点原子恢复；检查点之后新增的文件保留（不删除）；
  `revert` 仍属 `latex_write_tools` 的 ask 门（lab/sign 人审）。

## 二、远端同步（新模块 `src/company_agent/latex_sync.py`）

- 复用计划中枢 GitLab 客户端（`plan_hub`）的 fail-closed 解析、token 校验与 allowlist（同一套环境变量）。
- `company_latex_pull {project, repo}`：`GET repository/archive.tar.gz?sha=HEAD`（≤16MB）；
  tar 解包安全规则：顶层目录必须是合法 `repo-sha` 名（拒绝 `..`）、成员拒绝符号/硬链/绝对路径、
  只落受管后缀（源码+图形）、路径逃逸即抛错、每文件 ≤2MB、合计 ≤50MB、文件数 ≤300、现有文件原子替换。
- `company_latex_push {project, repo, message, branch?}`（ask）：读 GitLab `repository/tree` 判定
  create/update，动作以 base64 提交（POST repository/commits，分支默认 main）；只增改不删（删除留人工）；
  超出预算诚实报错提示改走归档流程。回传 ≤64hex commit id。

## 三、合同改动（仅 5 个既有工具行，工具总数不变）

`company_latex_diff / checkpoint / revert / pull / push` 的参数与输出 schema 从"unconfigured 桩"
改为上述真实形状（全部 `additionalProperties: false`、字段长度/条数上限、`repo` 复用 allowlist 语义）。
计数钉不受影响（11 个 latex 工具、50 总工具数在并行会话新增两个工具前即成立）。

## 四、测试与门禁

- 新增 `tests/test_latex_runtime.py`（10 用例）：
  checkpoint→edit→diff→revert 往返、12 检查点滚动淘汰、非法 revert 目标拒绝、快照目录对扫描不可见、
  pull 只写受管后缀与逃逸拒绝（`../` 成员抛 `PlanError` 且不落盘）、pull 未配置诚实失败、
  push create/update 判定、message 非空与 allowlist 写门、push ask 门。
- 全量默认范围 pytest（并行会话同批 52 工具版本）：**994 passed / 1 failed / 2 deselected**；
  唯一失败 `test_bridge_behavior.py::test_bridge_waits_for_child_exit_on_failure[timeout]`
  为双会话高压并行下的时序波动，单文件复跑 **18/18 通过**，非本批引入。
- `scripts/verify_dsh_profiles.py` 实测 8 会话全部 ok；本人文件 ruff 全清。

## 五、边界

- 快照与远端提交都不做删除；`push` 若超出 base64 预算建议改走 ZIP 归档人工上传。
- `pull` 会以远端为准覆盖现有受管文件（设计即"远端为共享权威"）；对未推送的本地编辑，
  请先 `checkpoint` 或 `push`，避免直接 `pull` 冲掉。
- 并行会话的 `tenants / table_profile / workspace_reference / portal_bridge` 等批次归属其自身批文与门禁。
