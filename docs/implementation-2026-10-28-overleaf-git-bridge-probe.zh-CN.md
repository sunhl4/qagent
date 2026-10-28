# Overleaf Git 桥接联动 — 实现记录（2026-10-28）

## 背景

本线延续 `b015c964-0c2a-4b87-80c2-959f5cacebf3` 对话读取的公司教程
`D:\Yaozheng\AI操控Git与Overleaf教学文档.md`（内网 AyakaLeaf「通过 Git 桥接操控
Overleaf」方案）。截至 2026-10-27，教程的核心能力已全部落地为一条完整竖切：

- 合同：`contracts/tools.json` 中 `company_latex_overleaf_pull` /
  `company_latex_overleaf_push` / `company_latex_overleaf_status`
  （capability `company.latex`，操作 `latex.overleaf_*`）。
- 适配器：`src/company_agent/overleaf_sync.py`（fail-closed 客户端、浅克隆上限、
  遍历与符号链接拒绝、原子替换写入、令牌只在内存并全程脱敏）。
- 转发：`src/company_agent/latex_workspace.py` / `invoke.py` / `catalog.py`。
- 审批：`quantum_device_run` 同级的人审 ask 门 ——
  `packages/company-agent-policy/src/index.js` 的 `ASK_ROUTED_TOOLS` 含
  `company_latex_overleaf_push`，其审批理由含 project / project_id / branch；
  `src/company_agent/policy.py` 同步列出。
- preset 可见性：`contracts/presets.json` —— lab 全量三工具；algo 只保留只读
  latex 探针、不含 overleaf；sign 不含 latex。
- 测试：`tests/test_overleaf_sync.py` 等 67+ 项全绿（含 push 永不删除远端文件、
  错误文案不携带敏感词的 fail-closed 断言）。

## 本轮增量：部署探针

新增 `scripts/probe_overleaf_git.py` —— 部署方用于核对适配器环境合同的只读验收
探针，参照 `probe_model_service.py` 的证据惯例：

| 检查 | 内容 | 是否联网 |
| --- | --- | --- |
| config_shape | base URL 必须是裸 http(s) origin、令牌经 `COMPANY_AGENT_OVERLEAF_GIT_TOKEN` 提供、可选 allowlist（逗号/分号分隔的 hex project id，空值 = 不限流）且被探针项目命中 | 否 |
| authentication | `git ls-remote --heads` 通过派生的桥接 URL 认证成功（用户名固定 `git`、令牌只作为子进程 URL userinfo） | `--live` |
| branch_present | 目标分支存在于在线 head；证据只记录 40 位 head SHA | `--live` |
| refs_shape | 引用列表有界（≤1000）、格式良好 | `--live` |

语义：

- **离线默认**：不带 `--live` 不发任何网络请求,证据记录 `executed: false`；
  配置通过则退出码 0,否则 1（fail-closed）。
- **只读**：只跑 `ls-remote`,绝不 clone / fetch / push,不读工作区。
- **脱敏**：证据文件不含令牌或带路径的 URL；令牌与 base URL 在 git 输出中
  统一替换为 `[token]` / `[overleaf]`（复用适配器 `_scrub`）。
- **配置复用**：直接复用 `company_agent.overleaf_sync._configured` /
  `_remote_url` / `_run_git`,保证探针与适配器的校验语义永远一致。

用法（PowerShell）：

```powershell
$env:COMPANY_AGENT_OVERLEAF_GIT_TOKEN = "<Git Token>"
python scripts/probe_overleaf_git.py `
  --base-url http://192.168.110.71:8001 `
  --project-id 6adf1c08fafe5c0709551110 `
  --live --output docs/evidence/overleaf-git-probe.json
```

## 测试与门禁

- `tests/test_overleaf_probe.py`（新增,7 项）：
  离线记录 `executed: false`、缺凭据 fail-closed（退出码 1）、allowlist 未命中
  fail-closed、对关闭端口 `--live` 的 `ls-remote` 拒绝被记录且证据无令牌、
  真实本地 git 仓库 `ls-remote` 的 head 列表解析（只收 `refs/heads/` 并去重）、
  超界引用列表拒绝、令牌从传输错误中脱敏。
- 回归:`test_overleaf_probe` + `test_overleaf_sync` + `test_latex_runtime` +
  `test_invoke` + `test_contracts` + `test_policy` 合计 74 项全绿。
- 环境备注（存量,与本次无关）：本机 ruff 0.15.12 对任何含非 ASCII 的
  Python 文件误报 E902 `stream did not contain valid UTF-8`（未改动的
  `src/company_agent/invoke.py` 同样中招,文件本身经校验是合法 UTF-8）；
  与 2026-10-27 一轮的结论一致,暂不处理。

## 规则对照

- DSH 仍是唯一 Agent Runtime;探针是与运行时无关的一次性脚本,不新增循环。
- 未修改任何工具 schema,合同测试与 DSH 注册无需同步。
- 令牌不落盘、不进结果;工具结果保持短小（head SHA 为唯一的网络侧事实）。

## 本轮增量：pull 的本地编辑保护（教程模板二/三、第 6 节）

教程要求同步前「保护已有未提交内容」「遇到会覆盖内容…说明具体位置」。此前
`company_latex_overleaf_pull` 无条件用在线快照覆盖工作区同名文件，本地修改
会被静默替换。本轮把 pull 改为差异感知、默认 fail-closed：

- **合同**（`contracts/tools.json`）：`company_latex_overleaf_pull` 输入新增
  可选 `force`（boolean）;输出新增可选 `overwritten`（0..300,被覆盖的本地
  差异文件数）与 `checkpoint`（chk- 快照 id,仅覆盖发生时出现）。required 列
  表不变,老调用形态不受影响。
- **适配器**（`src/company_agent/overleaf_sync.py`）：浅克隆后先比对在线与
  工作区同名 managed 文件;存在内容差异时,不带 `force` 直接 `PlanError` 并
  指出位置（前 3 个路径+Bounded 长度）;带 `force` 时必须先经工作区层回调把
  将被覆盖的本地字节快照进 `.latex-snapshots/checkpoint`（复用快照命名、
  cap 与轮转）,再写入在线内容。换行差异（CRLF/LF）不算丢失编辑——桥接
  `git` 在 `GIT_CONFIG_NOSYSTEM=1` 下按提交字节取回,而 Windows 文本写入
  会落成 CRLF;判定按归一化比较,覆盖仍写入在线原始字节（与 Overleaf 存储
  一致）。快照备份保存的是覆盖前的本地原始字节。
- **工作区层**（`src/company_agent/latex_workspace.py`）：新增
  `_overleaf_pull_backup`,生成 `chk-<utc>-<6hex>` 快照目录,note 固定为
  pre-overleaf-pull backup;`company_latex_revert` 可恢复其中的 LaTeX 源
  （revert 语义不变,图片按快照目录原样可取）。
- **policy / DSH**：pull 仍是 lab/algo allow 的读向操作,`force` 不改变审批
  通道（可恢复快照保证了回退路径）；插件按合同透传,注册无需改动。

### 门禁

- `tests/test_overleaf_sync.py` 从 11 项扩到 18 项：无差异 `overwritten=0`、
  本地差异默认阻断且消息含路径与 `force` 提示、纯换行差异不阻断且改写为在
  线字节、`force` 生成快照并返回合法 `chk-` id、缺备份回调拒绝、走 `invoke`
  信封的错误透出、结果通过输出合同校验（含 unknown fields 拒绝）。
- 回归:`test_overleaf_sync` + `test_overleaf_probe` + `test_contracts` +
  `test_invoke` + `test_latex_runtime` + `test_policy` + `test_schema` +
  `test_workspace_files` 合计 111 通过 / 2 skip（既有 live 项）。
- `test_bridge_behavior` 在本机仍不可运行（POSIX 专用,要求
  `scripts/bootstrap_dsh.sh` 预置的 pinned DSH Node;WSL 侧还观察到 drvfs
  对本会话新写文件的陈旧缓存）,属环境限制,与本次代码无关。
- ruff E902 误报为存量环境问题,本轮新增代码均为 UTF-8 合法且 pytest 全过。

## 本轮增量：latex push → plan hub issue 附 PDF 联动

落地[计划中枢记录](implementation-2026-10-26-plan-hub.zh-CN.md)「诚实边界与后续」
声明的后续批次：Agent 在人审后把本地编译出的论文 PDF 作为附件挂到 GitLab
issue 评论，形成「修改 → 推送 → 组长验收」的闭环通道。

- **合同**：新增 `company_latex_issue_note`（capability `company.latex`，
  operation `latex.issue_note`，人审 ask 路由）。输入 `project`/`repo`/
  `issue_iid`/`artifact`/`note` 全部必填，`artifact` 必须位于
  `.latex-build/` 下且以 `.pdf` 结尾；输出 `{project, repo, issue_iid,
  note_id, attachment}`，`attachment` 钉为 `/uploads/...` 相对链接（拒绝
  绝对 URL）。`company.latex` 工具数 14，lab 可见工具 59，合同工具 59。
  `policy.json` 的 `latex_write_tools` +1（ask lab/sign、deny boot/algo）。
- **内核**：`plan_hub.py` 抽出共享的 `_open_json` 响应映射（401/403/404/4xx/
  5xx→既有通用短语，逐字不变），新增有界 `upload_project_file`（multipart
  POST `/uploads`，附件 ≤10MB，文件名白名单，返回相对链接校验）；
  `latex_workspace.py` 新增 `issue_pdf_note`（工作区路径拒绝逃逸/符号链接，
  上传字节即编译产物原文件）。
- **DSH 插件**：`company-agent-policy` 的 `ASK_ROUTED_TOOLS` 与审批理由模板
  加 `company_latex_issue_note`（project/repo/issue_iid/artifact）。
- **顺带硬化（本轮触发的真实缺陷）**：
  - `runtime.js` 子进程环境固定 `PYTHONUTF8=1`——CLI 信封是 UTF-8，在 GBK
    控制台主机上否则中文事实会乱码回传；
  - `package-agent-core` 的 stderr 尾部缓冲改为 Buffer 块累积（早前一轮），
    `parseCliOutput` 拿到的是真实原始尾字节；
  - `knowledge.py` 的 `_installed_knowledge_root` 只在候选
    `quantum-capability.md` 真实存在时返回——`pip install --target` 布局下
    dist-info 定位会算出 `site/../..` 的不存在路径并抢先驳回真实前缀回退，
    wheel 门因此整批失败；
  - 桥接测试与 wheel 门的子进程显式按 UTF-8 解码（`text=True` 在 Windows
    上走 GBK 代码页），`test_installed_wheel` 的最小 env 保留父级运行时
    支持（仅剥离 `PYTHON*`/公司凭据键并重钉 `PYTHONPATH`），独立性主张
    （合同仍来自 wheel 打包面）不变。
- **门禁**：新增 `tests/test_latex_issue_note.py`（11 项：合同接线、lab ask
  →approved 流、multipart 上传含 PDF 字节与文件名、单条 note 正文体、凭据
  不回显、`.latex-build` 之外/缺失/超尺寸 artifact、绝对链接拒绝、5xx、
  参数信封 fail-closed）。计数钉同步：`test_receipts` 审批清单（17 项）、
  `test_plugin_runtime` 目录 59 与 latex 注册名单、`test_verify_dsh_profiles`
  company-agent 探针 67、`test_installed_wheel` 工具 59/能力 13 并修正其
  最小 env。合并域合计 `contracts/invoke/plan_hub/overleaf_sync/
  issue_note/policy/receipts/plugin_runtime/schema/latex_runtime` 192 项全绿。
- **已知环境项（非本批，如实记录）**：`test_bridge_behavior`（POSIX 专用，
  需 `bootstrap_dsh.sh` 预置 pinned DSH Node）、`verify_dsh_profiles` 的
  start_runtime.sh 拒绝探测与 minimal node_modules 拷贝断言（同因）、
  `release_manifest`/`manual_evidence`（`os.O_NONBLOCK` 与只读根断言，属
  发行批次的 POSIX 假设）、`knowledge/tenants` 符号链接用例（Windows 需要
  symlink 特权）、`no_legacy`（并行会话根目录临时物）。

## 本轮增量：加密旁路开关 + 真实传输 E2E（教程第 1–5 节全链）

目标：按[教程](../../../AI操控Git与Overleaf教学文档.md)「内网 HTTP、不引入
TLS」的现实部署，把 Overleaf 竖切做完并补上端到端门禁。

- **加密旁路（显式开口、默认 fail-closed）**：`plan_hub._base_url` 新增
  环境开关 `COMPANY_AGENT_GITLAB_ALLOW_PLAINTEXT=1` —— 允许公司内网
  plain-HTTP GitLab；默认值不变（loopback 之外必须 https），开关只挡住
  「必须加密」这一条并保留全部响应映射。测试
  `test_plain_http_outside_loopback_opt_in` 双向钉住（默认拒、开口后走
  既有 fail-closed 短语）。Overleaf 桥接 URL 校验本就允许 http origin，
  无需改动。
- **真实传输 E2E（离线全链）**：新增 `tests/test_overleaf_e2e.py` ——
  与既有 `test_overleaf_sync`（stub `_remote_url`）不同，它把
  ``git http-backend`` 起成回环 CGI 服务，扮演部署方 AyakaLeaf 桥接的
  真实 smart-HTTP 传输；全链 status → 差异守卫 → force pull（带覆盖前
  快照）→ 编辑 → push（远端裸仓验证内容）→ no-op push 拒绝，另含
  错误令牌 fail-closed 与结果不含令牌/地址断言。3 项全绿、全程
  127.0.0.1。桥接服务器行为对齐部署语义：所有 `/git/` 路径先 401
  challenge 再校验 Basic（用户名 `git`、密码=Token），错令牌与无令牌
  都被拒，401 响应关闭连接防挂起。
- **修复由 E2E 挖出的部署面缺陷**：`overleaf_sync._remote_url` 以前对
  无路径 base 直接返回根 URL（`http://git:tok@host:8001/`），真实克隆会
  打到服务根上既不走 `/git/<id>` 也不失败（`tests/test_overleaf_sync`
  用 monkeypatch 把这条线上次悄悄盖住了）。现在钉住教程 URL 形态
  `<base>/git/<project_id>`（反向代理解也保留其前缀），并新增
  `test_remote_url_keeps_canonical_git_bridge_shape`。修复后 clone
  0.56s / status 0.55s 直达。
- **live E2E 门（opt-in、只读）**：新增 `tests/test_overleaf_live_e2e.py`
  + pyproject marker `overleaf_live`（默认 addopts 排除）。部署方在
  `COMPANY_AGENT_OVERLEAF_GIT_BASE`/`_TOKEN`（可选
  `_E2E_PROJECT_ID`）就绪后 `python -m pytest tests/test_overleaf_live_e2e.py
  -m overleaf_live` 即可跑真实部署上的「新鲜工作区 pull + status「
  （工作区=在线，total 0）与错令牌 fail-closed 两条；push 仍留在工具层
  人审 ask，不做自动化。无凭据时两条诚实 skip；默认范围全数 deselect。
- **门禁计数**：受影响族合计 29（overleaf 族）+ 44（plan/issue）+
  … 合并域 `contracts/db/plan/policy/receipts/plugin/runtime/latex/
  issue/e2e` 于本轮累计 196+29 全绿；`pyproject` 的 markers/addopts
  同步（平行的 `posix_permissions` 钉保留）。
- live e2e 属机器上无凭据环境，最终部署侧只需两枚环境变量加一条
  pytest 命令。
