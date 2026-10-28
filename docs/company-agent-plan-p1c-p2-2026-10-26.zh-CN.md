# P1 批次 C / P2 侧执行记录：租户注册表与开通事实投影（2026-10-26）

依据：[约 2000 人天计划](company-agent-2000-person-days-development-plan-v1.0.zh-CN.md) P1「租户/服务开通」与 P2「工作台状态面」；沿[P1-A](company-agent-plan-p1-step1-2026-10-26.zh-CN.md)、[P1-B](company-agent-plan-p1-step2-2026-10-26.zh-CN.md) 的合同→适配器→测试顺序。

## 1. P1-C：租户注册表与开通事实（本批次核心）

**合同**：新增 `contracts/tenants.json`（契约形状：registry_env、regimes、states、services、line_fields、reasons、预算四项）；`catalog.py` 合同清单 `_CONTRACT_NAMES` + 精确门禁、`scripts/release_manifest.py` 的 CONTRACT_NAMES 同步新增 tenants。合同 digest 相应变更为 `sha256:c6e9b744…a3`（合规证据已绑定）。

**适配器**（`src/company_agent/tenants.py`，新模块）：

- 注册表为运维管理的 JSONL ledger（`COMPANY_AGENT_TENANT_REGISTRY` 指定；绝对路径、非符号链接、≤1MB、≤1024 行），行形状严格 `{subject, service, state, expires_epoch(null=不限), approved_by}`；任何坏行→整表 `unavailable`（与 knowledge/skills registry 相同的失败闭合纪律）。
- 三种投射事实：`legacy-single-user`（未配置 env：保持演示单用户行为，services 为空、无事实）；`registry`（按行序最后一条决断，approved+未过期才 enabled；reason=approved/pending/revoked/expired/subject_absent/untrusted_subject）；`unavailable`（配置但无效：四项 enabled=false、reason=registry_unavailable）。
- **关键失败闭合点**：`untrusted` 主体永远不消费注册表行——即使注册表里存在字面 `unknown@unknown` 条目，也不可成为匹配来源；测试明确钉住。
- 服务范围严格限四项外部服务（company.algorithm / company.asset / compute.cloud / compute.hpc）；enitlement 不改变 visible_tools、不改 policy ask/deny；审批仍由 policy 与平台决定。

**投影**：`company_capabilities` 信封新增 `enablement`（regime/subject/services×4），输出 schema 同步（受控枚举 + additionalProperties:false；approved_by/expires_epoch 采用"键省略=未知"而不是 null 字段，遵循现有 schema 子集无联合类型）。首次落地时引入 `$ref/$defs` 与 `["integer","null"]` 联合均被合同 schema 子集拒绝，改为内联展开与键省略——教训记入批次👨 review。

## 2. P2 侧：工作台/doctor 呈现开通事实

- `company-agent doctor`：新增 `tenants_governance`（regime/configured/valid/entries/subjects/approved_services，仅计数与布尔，无 subject/无路径）。
- `apps/company-workspace/host.mjs` 只读投影端点透传 `tenants_governance`；`client.js` 平台行新增开通状态语（"开通 注册表 N 项有效 / 未生效 / 旧单用户模式"）。
- UI node 套件 **29/29 通过**（含 layout 白名单）。
- 模型服务六点验收（P2 5.2）：2026-10-23 已落地且本轮无变化；本地 DeepSeek 端点离线补测仍是等待项。

## 3. 测试与门禁（不含全量）

- `tests/test_tenants.py`（新）：**18 passed**——legacy/registry/unavailable 三态、最后行决断、四服务之一或部分、过期/撤销/待批准、untrusted 不匹配、坏行失败闭合、缺失/相对路径/符号链接/超行/坏形状、payload e2e（registry 与 legacy 形态）、doctor 聚合（legacy 与计数）。
- 定向回归：`receipts/contracts/policy/contract_upgrade/cli/installed_wheel/contract_upgrade/invoke/workflow/plugin_runtime` → **208 passed**。
- 合规门禁：场景 15 → **17**（`tenant-registry-enablement-projection` 与 `tenant-registry-invalid-fails-closed`），**17/17 ok**，证据重生成。

## 4. 边界与下一步

- registry/归档文件的运维写入端（host.mjs 演示批准→注册表行）与真正企业 IdP 仍是 P1 余下部分；演算接线将以"演示批准生成 approved 行 + 服务到能力映射解析（compute.cloud/hpc ↔ 演示 kind）"落地，但需先与 workspace 现有 grants 存储形态核对后再动 UI 代码。
- enablement 是**事实投影**，不是授权：没有 registry 事实时不会给旧演示加门，也不会给企业加鸟能力。
