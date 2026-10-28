# 公司工作台自定义审计：主流对齐与自动化演进（2026-10-22）

范围：`apps/company-workspace` 演示壳及配套（外层组合替换、设置归位、接入接缝、布局状态、中栏沙箱、演示门禁、主题投影、门禁测试）全部现存自定义。判定问题两个：**是否符合主流方式**（含演进方向）、**是否适配后续全自动工作流**。

## 0. 判定锚点（每条判断的依据来源）

| 锚点 | 内容 | 用途 |
| --- | --- | --- |
| DSH 0.1.5-rc.3 包契约（最高优先权重） | `dsh-client-ui-*` 包内 README + `lib/types/client/contract/slots.d.ts`（运行时安装树内自带） | 原生"设置/侧栏/插件"为什么长这样、扩展点在哪，是上游说的，不是我们猜的 |
| OpenAI Help Center「Connected apps in ChatGPT」（help.openai.com/en/articles/11487775 及 collections/12923329） | 第三方服务连接在设置内是**独立分区页**；含 app permissions、action approvals、provider access、workspace settings 四类 | 「平台连接」自有分区页的行业同构证据 |
| VS Code / DeepSeek 网页版 / Cursor 的设置信息架构 | feature-owned section（扩展自持页面）；视图类开关留在界面自身，不进设置 | 布局控制不进设置的惯例证据 |
| 本仓 OSS 调研 A 卷（`docs/oss-survey/A-汇总-权限门对比.zh-CN.opo.md` 不存在；正确路径为 `docs/oss-survey/A-汇总-权限门对比.zh-CN.md`） | ask/deny 三态、审批记忆、失败闭合的主流 harness 对照 | 自动化审批链路不做第二套记忆的依据 |
| 本仓合同与硬规则 | `docs/ARCHITECTURE.md`、`AGENTS.md`、结果预算凭据红线 | 演示壳零工具循环、凭据不进对话的合规依据 |

## 1. 逐项审计

### A. 外层组合替换（`host.mjs` `REPLACED` = ui-layout + ui-sidebar）

- **现状**：boot manifest 整条过滤两包、注入演示壳客户端；对话/会话/主题/localize 渲染工厂原样装载；`?native=1` 一键回原生。
- **主流对齐**：compose-not-fork。替换点只发生在组合层（上游 README 声明的 manifest 注入协议），不改上游文件；升级安全靠"组合前存在性检查 + 失败闭合"（`'Unsupported DSH shell manifest'` 抛错）。业界同类（VS Code 简化/完整界面切换、网页版多入口共存）都保留双轨切换。
- **自动化演进**：对话入口键、会话持久化、审批生命周期全部留在原生层，意味着 CLI/API/无头入口（`docs/implementation-2026-10-21.zh-CN.md` §5）与网页是同一运行时；我们的壳不挂任何工具，纯 presentation，自动化不需要浏览器。
- **钉桩**：`tests/ui/shell-host.test.mjs`「boot composition replaces only outer layout/sidebar and preserves native conversation URLs」。
- **回退/升级成本**：从 `REPLACED` 表删两行即回原生；升级 DSH 时若两个组件 id 消亡会启动即抛错（诚实失败，不静默半装载）。

### B. 设置归位（`settings.section` id `platform` order 12 + `settings.general.item` order 25 发现行）

- **现状**：平台连接 = 原生设置对话框自有分区页（云/超算卡片：申请开通、连接状态、凭据说明）；通用区一行做发现端（同语言/外观行先例）。
- **主流对齐**：①OpenAI Connected apps 锚点：连接域即独立设置分区页（同构）；②DSH 契约原文："A feature owns its own settings pages — adding a setting never means editing the shell"（`ui-settings` README）以及 General 行定义（`slots.d.ts`）；③插件分区语义不符的直接证据：`settings.plugin.item` 按 settings 命名空间取键、只列宿主平面插件（`ui-settings-plugins` README），本部署无 browser 半侧 plugin，塞进去就是死代码——事实证明确实死了（曾注册 `plugins.item` 零命中）。
- **自动化演进**：页内所有状态都是服务端端点投影（§C），无头流程直接调 API，不需要打开设置对话框；无编程深链是 DSH 现状（`openSection` 仅引导流程内部传递），我们**没有发明旁路 API**，未创建第二套开壳状态——这是自动化友好关键（所有能力门在服务端，GUI 只是投影）。
- **钉桩**：文案/跳转语义由 `workspace-prototype.test.mjs`「platform connection management lives in native DSH Settings」钉住；HTML 无 set-in-page 表单断言。
- **回退/升级成本**：注册即注入（`ctx.slots.inject` 跟随分区延迟声明）；DSH 升级若 slot 兼容点变化，只需审查这两处注册调用。

### C. 接入接缝（`docs/company-workspace-access-seam.zh-CN.md` v1 + 信封钉桩）

- **现状**：申请（`POST /access`）→ 管理员（`x-admin-token`，0600 密钥文件）批准（`POST /access/grant`）→ 凭据写服务端配置（0600）→ 状态布尔投影。`account` 字段为公司内部客户端/SSO 预留。
- **主流对齐**：服务端托管凭据、客户端零经手是 GitHub/GitLab 类工作区的通行形态（runner token、enterprise app 均走管理员授予 + 服务端注入）；OpenAI 的 workspace controls 同构（管理员层审批，用户层只看状态）。
- **自动化演进**：这是本清单里全自动工作流**最关键**的一格——grant 是 API 不是 GUI 动作，未来排班机器人/CI 可以无人值守完成开通；审批细则（谁批、哪个请求 id）归内部客户端持有，"人管授权、机器只用状态"。所有响应形状被测试钉死，替换实现时的形状漂移会被 CI 拦截。
- **钉桩**：`shell-host.test.mjs`「access seam keeps its documented client-facing envelope」（形状级）；正文契约 + 换入清单在 seam 文档第 4 节。
- **回退/升级成本**：服务端实现的换入不动前端；文档明列 6 条替换红线（403/400 语义、失败闭合）。

### D. 布局控制与 `localStorage: unitqc.workspace.layout.v1`

- **现状**：三栏开关/焦点/重置 + 几何持久化。
- **主流对齐**：视图偏好 per-browser 持久化是行业标配（VS Code workspace state 同类）；且**只存几何**，无业务状态——前端零业务存储由测试反向钉住（知识/开发/门户等页断言 `localStorage/sessionStorage/cookie` 均空）。
- **自动化演进**：布局属视图格式，对工作流零影响；Profile 级布局（未来无头部署不需要）天然不参与服务端状态。
- **钉桩**：`layout-model.test.mjs`（几何求解）+ 上述内容页空存储断言。
- **回退/升级成本**：`model.restore(null)` 即默认布局。

### E. 中栏内容 iframe（同源 sandbox + CSP 收紧 `frame-src 'none'` + 单向消息白名单）

- **现状**：内容页同源嵌入；`company-content-open` 是唯一消息（壳→内容声明当前视图）。
- **主流对齐**：MDN iframe sandbox 原则（同源脚本沙箱、不隐藏式安全），宿主 CSS 与事件隔离是 iframe 集成底线；CSP 从 `frame-src http://127.0.0.1:3081` 收紧为 `'none'` 防内容页反嵌。
- **自动化演进**：消息面已收敛到一条单向声明（曾存在的双向 `company-content-nav` 桥因目标面板不存在已删，诚实闭合）；未来若需要内容页指示壳，走同一通道扩展一条受枚举校验的消息即可，不再虚构导航目标。
- **钉桩**：`shell-host.test.mjs`「UI assets require native auth and exact trusted origin」（403/401 矩阵、不含原生 iframe 标记、origin/source 校验断言）。
- **回退/升级成本**：内容页是纯静态注入，上游升级无牵连。

### F. 演示门禁（`scripts/dsh-cli.mjs`：production / 非 lab-sign 全拒绝演示壳）

- **现状**：`COMPANY_AGENT_DEMO_UI=1` 仅在 development + 正确组合放行；production 任何组合拒绝；最小组合 `lab/sign` 维持启动拒绝语义。
- **主流对齐**：演示环境与权限面分离（预览/演示环境不携带生产凭据；演示权限降级是显式的 env 选择而非意外）；失败闭合（"Workspace demo UI requires development…" 是唯一拒绝门文案，无旁路 env 组合）。
- **自动化演进**：全自动工作流走 CLI `invoke` 与 preset 策略（boot/algo deny 设备、lab 逐次 ask）——**与 GUI 同一内核同一审批**，演示壳的存在与否不影响自动化能力面；真实验收的"界面退出 ≠ 通过"红线未被触碰。
- **钉桩**：`shell-host.test.mjs`「presentation overlay cannot activate in production or device profile」（两个 spawnSync 场景，含 gate 文案匹配）。
- **回退/升级成本**：`COMPANY_AGENT_DEMO_UI` 缺省即原生脸，无需任何代码改动。

### G. 主题/字号投影（`client.js` 只读镜像原生 token）

- **现状**：`document.body` 投影原生主题 token 与 `--dsh-content-font-size`；不注入任何 CSS 进原生对话、不重绘原生控件。
- **主流对齐**：外层壳把原生主题 token 与字号读为 root CSS 变量，属于跟随宿主皮肤的读侧投影；"隐藏/裁剪/改写原生控件"是 v0.5 baseline 与 A 卷共同确立的禁区，我们只在自有容器内发言。
- **自动化演进**：与自动化无关（无头进程无此投影）。
- **钉桩**：`workspace-prototype.test.mjs`「right column loads the unmodified native DSH origin without recreated controls」（无自绘控件/无待接入文案）。
- **回退/升级成本**：投影函数一个。

### H. 第二套审批/onboarding/工具：不存在（负向审计）

- **现状**：演示壳客户端 require 列表只有 `slots/theme/locale`，未注册任何 tool、approval、onboarding；未挂载任何模型可见内容；演示服务器代码路径（`test_demo_server.py`）断言 env 不继承 `DEEPSEEK_API_KEY`/设备 token、preset 强制 boot/minimal。
- **主流对齐**：A 卷共识——审批与允许记忆只有一处真源；模型选择完全在原生「模型」分区，演示壳只读其投影；onboarding 完全未动。
- **自动化演进**：工作流脚本与 GUI 抢的是同一审批门，无旁路即"全自动也要过同门"——这是公司侧审计最看重的不变量。
- **钉桩**：`test_demo_server.py` 4 个隔离测试 + `verify_dsh_profiles.py` 组合矩阵（工具目录精确相等）。
- **回退/升级成本**：不在即无成本。

## 2. 结论

1. **主流对齐**：七项正向自定义全部能落到"上游包契约原文 + 业界同构先例"双证据；负向发现（曾存在 `plugins.item` 死代码与失效桥）已在本次归位完成改正，并纳入钉桩。
2. **自动化演进**：所有能力门（开通、审批、凭据、状态）都在服务端 seam 与 profile preset；浏览器层是纯投影 + 组合壳。今后搭建全自动工作流的增量方向是：服务端 seam 对接公司内部客户端、contracts/policy 增补分配策略——**不需要动 UI**，UI 已被定位为只读投影。
3. **遗留边界（诚实记账）**：
   - `client.js` 的设置分区声明目前未被 node 测试装载（属运行时组装），依赖手动浏览器验证（`COMPANY_UI_PLAYWRIGHT` 路径）；若要 CI 化，可给 `ctx.slots.register` 加形状钉桩——列为 M2 工作台方向，不在本轮扩张。
   - DSH 升级是唯一结构性风险点（`REPLACED` 存在性检查已把风险转为诚实抛错而非静默漂移）；升级时按 §10 记录的 slot 兼容点逐项复查即可，工作量估计 ≤ 1 天。
   - 设置深链依赖上游开放公开 API；若未来 DSH 提供 `openSettings` 面，中栏可恢复一键直达（但要注意：这不是自动化必需项，headless 全程无 GUI）。

## 3. 证据索引（快速回查）

| 断言 | 落点 |
| --- | --- |
| slot 契约原文（section/general/plugins 语义） | `~/.cache/unitqc-company-agent/dsh-runtime/node_modules/.pnpm/@deepseek-ai+dsh-client-ui-*` 内 `README.zh.md` / `slots.d.ts`（随 0.1.5-rc.3 装分发） |
| OpenAI Connected apps 锚点 | help.openai.com articles/11487775、collections/12923329 |
| 上游包/settings 演示壳门禁 | `scripts/dsh-cli.mjs` + `shell-host.test.mjs` 第三测试 |
| envelope 契约 | `docs/company-workspace-access-seam.zh-CN.md` + `shell-host.test.mjs` seam 测试 |
| 历史决策记录 | `docs/implementation-2026-10-21.zh-CN.md` §7/§8/§10 |
| Paper 自身 OSS 审批对照 | `docs/oss-survey/A-汇总-权限门对比.zh-CN.md`（注意：B 卷并行会话立档中，暂有 2 处 `test_no_legacy` 门禁未闭环，属该会话收尾，与本审计无关） |
