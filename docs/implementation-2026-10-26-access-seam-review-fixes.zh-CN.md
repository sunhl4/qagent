# Access seam 评审修正（2026-10-26，apps/company-workspace 批次）

对 2026-10-22「设置项归位 + 接缝契约」批次做逐处评审后的修正记录。每条都给出依据（对照 `docs/company-workspace-access-seam.zh-CN.md` v1 与 DSH 0.1.5-rc.3 pinned 源码），所有 UI 门禁保持可运行。

## 1. 授予端点恢复"仅管理员令牌"（合同 §2 对齐）

**问题**：`/company-workspace/access/grant` 的守卫在校验 `x-admin-token` 失败后**回退到浏览器会话检查**——任何已登录普通用户都能自我开通、甚至自带凭据写入服务端配置。接缝契约 §2 明文："grant 端点例外于浏览器会话席位：仅 `x-admin-token` 匹配服务端 0600 存放的密钥"。

**修正**：守卫改为 token-only；缺失/不匹配一律 `401 {"error":"unauthorized"}`，无会话回退。**依据**：合同 §2 的字面语义；同批钉入 `tests/ui/shell-host.test.mjs` 三个用例（无 token / 错 token 401，正确 token 200 且响应键为 `{granted,ok}`）。

**连带**：令牌比较改为 SHA-256 摘要上的 `timingSafeEqual`（恒定时间、不暴露长度/前缀时序信）。

## 2. 普通设置端点不再接受凭据（合同 §2 对齐）

**问题**：`POST /company-workspace/settings` 仍接受 `cloudKey` / `cloudKeyClear`——这是"用户自行粘贴密钥"时代的遗留面，与接缝契约 §2（POST 仅非敏感字段）和"用户不经手凭据"的新立场直接冲突；且与 grant 端点形成**两条**凭据写入路径。

**修正**：`saveSettings` 收窄为非敏感字段（cloudApi/cloudPortal/hpcPortal/hpcGateway/hpcUser/hpcHost），收到 `cloudKey` / `cloudKeyClear` / `hpcToken` 一律 400 并明确提示走「平台连接」申请；凭据唯一写入路径回到 grant 端点。**依据**：契约 §2 v1 的字面语义；钉桩用例断言 settings POST 带凭据 400、无凭据保存 200 且响应不含 sk- 值。

## 3. 内容页文案去除"用户索取 X-Api-Key"旧话术（3 处）

**问题**：`docs/quantum-agent-architecture.zh-CN.html` 中三段 honestBox / 状态条仍在指引用户"向云平台管理员索取 X-Api-Key 并写入服务端配置"——既与 §7 云平台链路修正（真实可用的是 sk- 前缀 key 走 SDK Socket.IO 探针，REST `/api/v1` 的 X-Api-Key 是另一层认证）结论相悖，也与统一开通流程（申请→管理员批准→服务端注入）相悖。

**修正**：三处文案统一指向「设置 → 平台连接」申请开通；`missing_api_key` 描述改为"本机服务端尚未持有云平台凭据"。**依据**：implementation 记录 §7（2026-10-21 下午，已验证）+ 本批 §1/§2 的凭据注入边界。

## 4. 验收脚本门禁与环境无关化 + 新增 fail-closed 钉桩

**问题**：`tests/test_acceptance.py::test_local_missing_runtime_blocks_all_gates` 对 `local_checks()` 的**全量输出**做精确相等断言，而脚本本年新增的 dev 依赖探测（`pytest`/`ruff`/`build`/`hypothesis` 缺失时逐项 `dependency_*` blocked）使该输出随解释器环境漂移：任何一台缺一个依赖包的机器都会让"缺运行时短路"用例失败。

**修正**：用例内 `monkeypatch` `importlib.util.find_spec` 恒真，保持"缺运行时 → 恰好一条 dsh_runtime blocked、不跑任何 gate"的确定性断言；另新增用例钉住"缺 dev 依赖 → 逐项 `dependency_<module>` blocked + `install_runtime_python_dev_lock`、仍不跑 gate"。**依据**：脚本行为本身是有意的 fail-closed（环境诚实报告），旧用例没有考虑环境漂移属测试缺陷，不是恢复旧行为。

## 5. 陈旧测试钉桩与 2026-10-26 并行批次的契约重同步

并行批次（`docs/implementation-2026-10-26-ui-receipt-contract.zh-CN.md` 与组合策略改动）把演示壳从"替换外层 layout/sidebar"改为"纯追加（additive）"，client 改走 `uiConversation` 子作用域；以下测试钉桩按**新契约**更新（不是回退旧行为）：

- `tests/ui/shell-host.test.mjs` boot 组合用例：改为断言"纯追加"语义——原生 entry 的 url/rev 逐字保留、公司模块仅追加在末尾且只注入 renderer/session/theme/locale 四个面、rev 加后缀、`?native=1` 完全不组合、守卫幂等。
- `tests/ui/layout-model.test.mjs` 客户端面用例：改名"additive client rides native slots"；断言注入面只有 `['slots','locale','sidebarRightTabs']`、回执只经 `ctx.inject(['uiConversation'], …)` 子作用域注册、设置席位钉住 `settings.section/platform/order 12` 与 `settings.general.item/platform-connections/order 25`、host 侧"additive、禁止 entries.filter/REPLACED"。
- `tests/ui/receipt-contract.test.mjs` ctx 垫片：`scope.get(name)` 改为**按名解析**（未注册名单 fail-closed 抛错），注入面断言同步为三个声明面。

## 6. 注释级补强（不改行为）

- `profiles/company-agent/cordis.patch.yml`：注明 `permissionMode: never` 是 0.1.5-rc.2 上游默认值的**有意重述**（防上游默认变化静默放宽），并由 `scripts/verify_dsh_profiles.py` REQUIRED 文本钉住；注明 `inheritsParentContext` 不是 config schema 键、真实保证在 provider 内部硬编码 false + 门禁 FORBIDDEN 工具检查（对照 `@deepseek-ai/dsh-subagent-codex` 源码 `Config` schema 与 `CodexProvider.inheritsParentContext = false`）。
- `apps/company-workspace/host.mjs` 云探针候选：注明解释器选择 env 优先、后两条为已知本机 venv 与系统的回退兼便，外机自动降级 python3。

## 7. 验证

- `node --test tests/ui`：31/31 通过（含本批新增 3 个 grant/settings 钉桩与重同步用例）。
- Python 套件与 `verify_acceptance` 本地模式结果见同批执行记录（`pytest tests` 全量）。
