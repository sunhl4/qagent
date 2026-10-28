# P3 批次 A1 执行记录：受管网页检索 company_fetch（2026-10-26）

依据：[约 2000 人天计划](company-agent-2000-person-days-development-plan-v1.0.zh-CN.md) P3「受管网页检索、内容注入隔离、来源引用和未完整扫描的显式状态」工作包。本批次按合同先行顺序新增了第一个带真实网络外呼的本地工具，默认状态为**零网络**：allowlist 缺失即构造性失败闭合，不依赖策略或运行时兜底拦截。

## 1. 交付

合同（先）→ 适配器（后）→ 测试/门禁：

1. `contracts/tools.json` 追加 `company_fetch`（capability `company.knowledge`，operation `web.fetch`，无句柄），输入仅 `url`（`^https?://`，\(\le 2048\) 字节），输出为有界短结果：`trust=untrusted_reference_data` 恒定、`text` \(\le 20000\) 字节、`body_bytes` \(\le 1000000\)、`scan.complete/reasons` 显式标记截断预算。同步更新 `capabilities.json`、`presets.json`（boot/lab/algo 可见，sign 不见；与 knowledge_search 同型）与 `catalog.py` 的期望工具名集合。
2. `src/company_agent/webfetch.py`：新南向模块 `fetch()`，全部失败闭合设计——
   - 仅 `COMPANY_AGENT_FETCH_ALLOWLIST` 可以启用外呼；缺失/空/畸形条目直接报错，零请求发出。条目只接受精确主机或一条前缀 `*.` 通配，\(\le 16\) 条，拒绝非法字符、`*` 置中和 IPv6 写法。
   - 单请求语义：不跟随重定向（专用 opener 关闭跟随，3xx 一律报错）、禁代理（`ProxyHandler({})` 防 allowlist 被环境代理绕过）、只允许 `text/plain` 与 `text/html`、`http` 仅限回环地址、全部解析地址必须公网（`ipaddress.is_global`），唯一例外是**允许表显式点名回环字面量**（离线测试与开发用途）；`localhost` 名称与私有网段一律拒绝。
   - HTML 正文按数据提取：script/style 内容丢弃，空白折叠、UTF-8 解码 `errors=replace`，字节安全截断（在字符边界裁剪，不留半个字符）；比预算截断记录 `byte_budget`/`body_budget` 原因，`scan.complete:false` 显式承认未完整捕获。
3. `invoke.py` 注册 `_LOCAL_TOOLS`；错误消息经 `_safe_error_message` 保持无 URL、无主机、无正文。

## 2. 与 DSH 原生 web_search 的分工

`web_search`（模型后端搜索，共享托管模型凭据）不变；`managed_builtins` 中其描述同步改为「通用无管理网页抓取保持禁用，唯一受管外部页面读取是走 operator allowlist 的 company_fetch」——原句「web fetch stays disabled」已不再准确，避免合同自相矛盾。

## 3. 测试与门禁（不含全量）

- 新增 `tests/test_web_fetch.py` **18 项**：无 allowlist 关闭、非 allowlist 主机拒绝、明文成功路径（trust/scan 完整字段锁）、HTML 去脚本化、字节边界截断（中文坏截断用例）、1.6MB 正文体预算、重定向不跟随、content type 拒绝、404 无 URL 回显、`localhost` 名称拒绝、allowlist 私有字面量拒绝、通配匹配/容器畸形与 16 条上限、DSH 投影参数合同、lab/sign 预设决策与零回执、参数合同（schema 拒绝 ftp/空/多余字段）。
- 合同与既有定向（`test_invoke/test_contracts/test_catalog/test_policy/test_receipts/test_analysis/test_managed_builtins/test_review_20261008/test_no_legacy` 等）全绿；工具数钉 47 → **48**（CLI 完整目录末位 `company_fetch`、installed_wheel `48 1`、DSH lab 探针钉 55/5 → **56/6**）。
- 全量复跑：主仓 pytest **936 通过**（默认排除标记除外）、`tests/ui` node **29 通过**；期间发现并修正 `test_verify_dsh_profiles` 的探针计数钉一处。
- `scripts/compliance_gate.py` 新增 denied 场景 `web-fetch-allowlist-disabled`（17 → **18**）：无 allowlist 时 `company_fetch` 返回 error、错误声明 disabled 且 `company_fetch` 零 dispatch 回执——「零网络」由构造保证而非运行时观察。`docs/evidence/compliance-local.json` 重生成 18/18 ok，合同 digest 更新为 `sha256:fedefc1d…`。

## 4. 边界（诚实的不完整）

- 返回文本**尚未做注入扫描**：`trust=untrusted_reference_data` 是恒定标记（按 P8 验收语言：网页永远只是数据、不是授权来源），P3 后续批次需要加可验证的注入检测与来源引用结构，而不是依赖提示词。
- DNS 解析后 urllib 允许重连仍存在 TOCTOU 窗口（DNS 重绑定残余风险）；运营要求是 allowlist 指向内网固定解析的名称或字面量，P3 下一批次以 pinned DNS 方案消除该窗口。
- 字符集只走 UTF-8 `replace`（非 UTF-8 页面可能出现替换字符），IPv6 字面量与域名暂不支持（失效闭合），页尾截断语义已显式化。
- 2000 人天计划中云/HPC/真机 provider 工作不受本批次影响；官方 Codex `permissionMode: never` 边界未改动。
