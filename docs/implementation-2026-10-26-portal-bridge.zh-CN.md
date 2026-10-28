# 门户桥批次：把云平台网页与超算网页接上 Agent（2026-10-26，会话侧可打开）

选型（用户确认）：**会话侧可打开**——agent 在对话里交付「打开云平台 / 打开超算门户」的动作（kind + 站内相对路由），页面由工作区原生承载。UI 渲染由正在重设计的另一程序做；本批提供合同、受管只读工具、服务端事实与证据。

本批合同/adapter/插件/测试与门禁在本轮全部落地；剩余两项服务端事项按窗口排队（见「三」）。

## 一、落地记录（实际写入）

- 合同：`contracts/capabilities.json` 加 `company.portal`（kind `portal`、provider `company-portal`、tools `[company_portal_open]`、handles `[]`、approval `none`）；`contracts/tools.json` 加 `company_portal_open`（输入仅 `kind ∈ {cloud,hpc}`；输出 `{ok,kind,route,note}`，全部封闭对象；`route` 为站内相对路径、`note` 为短句，**无 scheme/绝对 URL**）；`company_capabilities` 输出的 `kind` 枚举加 `portal`；`contracts/presets.json` 将 `company_portal_open` 写入 `boot/lab/algo` 可见名单（`sign` 不见，保持最小对外面）。
- Adapter：`src/company_agent/portal.py`（零外发；只有 kind 闸与常量路由映射；未知 kind → `PortalError("portal kind is unknown")` fail-closed）；`invoke.py` 注册 `_LOCAL_TOOLS["company_portal_open"]` 且 `provider_state` 的 local kind 集合加 `portal`（不要求任何 env）；`catalog.py` canonical 名单 + `expected_providers`；`capabilities.py` kind/id 映射。
- DSH 插件：`packages/company-agent-core/src/index.js` 的 apply 列表加 `company.portal`（两个 profile 都挂载 core，可见性仍由 preset 名单裁剪）；策略插件不新增 ask 路由（只读导航 approval none）。
- 附带修复（按事实收口并行批次遗留的合同/夹具缝隙）：
  - `packages/company-agent-policy/src/index.js` 的 `company_latex_push` 审批理由模板补 `repo` 字段（合同已把 repo 列为必填，模板漏字）；
  - `tests/test_plugin_runtime.py`、`tests/test_dsh_lifecycle.py`、`tests/test_cloud.py`、`tests/test_installed_wheel.py` 的真实引擎/桥接夹具改为**每用例独立 turn 身份 + 独立回执目录**：终止预算按 turn 计，不再跨套件累积。此前共享默认 turn 已由重复套件累积到 invocations 209/上限 128、device_runs 49/上限 4（实测账本已核对，属测试环境真实损坏而非策略语义变化）；
  - `tests/test_plugin_runtime.py` 对 runtime.js invoke 调用的一处硬编码钉放宽为调用前缀（budget 批次在调用实参尾部追加了 turn 身份）。
- 门禁：`scripts/compliance_gate.py` 新增 3 场景（portal-open-fact 零派发与零 URL、portal-unknown-kind fail-closed、boot 无需审批），证据重生成 **22/22 ok**（`docs/evidence/compliance-local.json`）。
- 计数钉同步：`test_cli` 53 且 catalog 末位 `company_portal_open`、`test_installed_wheel` "53 1"/能力数 12、`test_plugin_runtime` lab 探针 53/末位、`test_contracts` 一致性与注册矩阵、`test_plugin_policy` latex push/revert 语义、`test_contract_upgrade` 快照合同 10 文件、`test_verify_dsh_profiles` 探针 61/9。新增 `tests/test_portal_bridge.py`（9 用例全绿）。

## 二、会话侧动作数据流（合同面）与实测证据

`agent → company_portal_open {kind} → {ok, kind, route: '/company-workspace/portal/<kind>/', note ≤120B} → DSH durable 工具结果`。卡片/导航由工作区消费 `route`（同源相对路径），登录与页面事件全部留在门户内。`company-agent-receipts` 视图会自动携带该行；`route` 键不命中回执屏蔽词；输出内容校验零告警；`company_capabilities` 的 provider_state 显示 local（不要求配置）。

实测证据（`docs/evidence/portal-bridge-2026-10-26.json`，受管访问实例 11 条路径）：`/company-workspace/{cloud,hpc}/{status,overview}` 四条 404——2026-10-21 批次后 `host.mjs` 中 `cloudStatus/cloudOverview/hpcStatus/hpcOverview` 函数、缓存与探针全部健在但路由注册被摘除（本批待还原，见三）；`/company-workspace/portal/{cloud,hpc}/` 均 200 且上游 SET-COOKIE 已按 `UQC_PORTAL_` 前缀隔离；HPC（OpenSCOW）前缀化静态面 200×3；云门户自身资产 `UI_component/...` **在上游即 404**（直接探测 `https://220.178.61.185:8443/UI_component/...` 同样 404，属运营方门户资产部署问题，agent 侧诚实降级）。

## 三、服务端剩余事项（按窗口排队，防止与并行批次互踩）

1. ~~`host.mjs` 四条只读投影还原~~——UI 重设计批次于 14:30 的写入中自行补齐了 `jsonRoute` 注册（当前 `host.mjs` 第 460-463 行确认在位），本批不再重复；live 复验时发现该批次仍在继续演进（写入 16:12/16:39，且 16:39 的组合在受管实例上有 app-boot 待服务诊断）。接续步骤：由 UI 批次得出组合绿后，本批的探针配方重跑：登录 cookie → `/company-workspace/{cloud,hpc}/{status,overview}` 应 200 且结构同 10-21 版；`/company-workspace/portal/{cloud,hpc}/` 200 + `UQC_PORTAL_` 前缀 cookie。
2. HPC 部署 runbook 建议：OpenSCOW `serverBasePath` 对齐 `/company-workspace/portal/hpc`，从根因消除页面内 `//api/auth` 逃出 iframe 前缀的断链；代理侧兜底桥（固定注入的 fetch/XHR 前缀修复）暂不落地。
3. 云门户上游资产断链为运营事项：登记至部署 runbook；`note` 文案诚实描述（无可用性断言，不伪装成功）。

## 四、边界与回归结论

- 本批零外发、零网络、无新会话/循环；`company.portal` 是纯本地事实能力，provider 不进 `providers.json`（与 plan/latex/knowledge 本地能力同型）。
- 回归：默认全量 pytest **1001 通过 / 0 失败**（含真实 DSH 引擎生命周期、cloud/HPC 提交闭环、plan/LaTeX/知识/预算/租户治理全部既有门禁），合规门 22/22，`tests/ui` 门禁侧三件套 + 门户契约 29/29 未受影响。
- UI 渲染、卡片样式与面板布局完全归 UI 重设计批次；唯一耦合面是合同的工具输出（kind+route+note）与四条只读投影路由（其注册已由该批次完成）。
