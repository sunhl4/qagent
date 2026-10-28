# P1 批次 B 执行记录：主体绑定固化进合规门禁（2026-10-26）

依据：[约 2000 人天计划](company-agent-2000-person-days-development-plan-v1.0.zh-CN.md) P1；[P1-A 批次记录](company-agent-plan-p1-step1-2026-10-26.zh-CN.md) 的延续。本批次不新增业务字段，只把 P1-A 的主体绑定不变量固化到持续合规门禁，并在固化中发现并修复一个潜在缺口。

## 1. 交付

`scripts/compliance_gate.py` 新增两个场景（总数 13 → **15**）：

1. `normal / subject-binding-trusted`：设置可信主体 env → `company_capabilities` 的 `identity` 显示 `subject=operator@corp.example.com`、`subject_source=trusted`；同会话写下的回执 dispatch 行必须携带同一可信主体。
2. `denied / subject-invalid-env-never-replaces-identity`：注入非法可信值（`op;rm -rf /`）→ 身份必须为 `unknown@unknown` + `untrusted`，禁止静默落回 OS 身份（多用户环境下等价于冒名归属）。

遵守固化规则：均为确定性断言，不引入模型判分；门禁证据 `docs/evidence/compliance-local.json` 重生成，场景指纹 `task_set_sha256` 随场景清单变化为 `bdfefeeb…`（证据文件内自持，无需外部登记）。

## 2. 固化时发现并修复的实际缺口

首跑新场景 `denied` 失败，暴露是个真实缺陷：`contracts/tools.json` 中 `identity.subject_source` 字段我写成了 `maxLength: 8`，而 `untrusted` 有 9 个字符——`.trim()` 前的 P1-A 门禁只命中 `derived`（8 字符）路径，`untrusted` 路径只在“可信值非法”时才走到。**这正是把不变量固化进持续门禁的价值**：单靠定向 pytest 的既有断言（用例执行过的是 derived 路径 + 直接调用 `subject()`）抓不到这个组合态。

修复：合同 `maxLength: 8 → 12`，合同先行；无代码改动。验证：门禁 `15/15`，且定向 `test_receipts/test_contracts/test_policy` 48 项持续通过。

## 3. 测试与门禁（不含全量）

- `python3 scripts/compliance_gate.py`：**15/15 ok**。
- 定向：`tests/test_receipts.py + test_contracts.py + test_policy.py` → **48 passed**。
- 未跑全量 pytest（按用户约束）。

## 4. 边界

- 服务开通、租户注册表、宿主把认证后主体写入 `COMPANY_AGENT_SUBJECT` 的接线仍等待身份 Owner；本批次不改变演示级 host.mjs 行为。
- 证据文件含 15 场景与新旧合同 digest 绑定，后续任何场景增删都会改 `task_set_sha256` 并重生成——这正是 P1 验证体系要求的可比较性。
