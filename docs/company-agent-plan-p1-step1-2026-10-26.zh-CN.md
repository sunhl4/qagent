# P1 批次 A 执行记录：受信任主体绑定（2026-10-26）

依据：[约 2000 人天计划](company-agent-2000-person-days-development-plan-v1.0.zh-CN.md) P1「身份、租户、服务开通和授权」；本批次为 P1 的身份地基，不依赖企业 IdP 输入。执行顺序遵循 AGENTS：合同 → Python adapter → DSH 插件 → 测试。

## 1. 本批次交付（合同先行的主体来源）

**合同**（`contracts/results.json` receipts `1.1 → 1.2`；`src/company_agent/catalog.py:614` 门禁字面量同步）：

- receipts 新增 `trusted_subject_env: "COMPANY_AGENT_SUBJECT"`。行字段集合不变（`subject` 原已有），因此旧 v1.0/v1.1 行按字段集校验仍可读；新行写 `version: "1.2"`。

**语义**（`src/company_agent/receipts.py` `_resolve_subject()` + 新 `subject_source()`）：

- `trusted`：宿主在服务端认证后通过 `COMPANY_AGENT_SUBJECT` 设置的值，满足合同 `subject` 形状（≤ `subject_max_bytes`，`_SUBJECT_PATTERN`）时采用；`company_capabilities` 的 `identity` 与回执 `subject` 均落到该值。
- `derived`：可信 env 未设置时回退既有 `getpass@hostname` 推导（单用户机行为保持不变）。
- `untrusted`：**可信值设置但无效时，绝不静默换成推导身份**——推导出的 OS 身份可能属于另一个用户；直接以 `unknown@unknown` 归属，回执/能力投影如实标 `untrusted`。推导身份自身不可用（如空 hostname、超长、控制字符剥离后仍不合法）同样 `untrusted`。

**适配器**（`src/company_agent/invoke.py`）：`company_capabilities` 的 `identity` 增加 `subject_source`；不新增 stderr 诊断字段（主体不进遥测）。

**DSH 插件**：零改动——`company.plan` 能力已由 `packages/company-agent-plan` 在并行批次中注册，`company_capabilities` 由合同驱动的 core 注册投影。

**合同/工具输出 schema**（`contracts/tools.json` `company_capabilities.output.identity`）：增加 `subject_source`（enum `trusted/derived/untrusted`），required 与 `additionalProperties:false` 同步——否则新增字段触发"未知字段失败闭合"的正确行为。落点即本次教训：**能力输出信封字段与合同 schema 两侧同时登记**。

## 2. 测试与门禁（不含全量，按用户要求）

- `tests/test_receipts.py`：**29 passed**。新增 4 用例：身份携带 `subject_source`；可信 env 同时绑定能力投影与回执行；无效可信值（含注入形状、超长）必为 `unknown@unknown`/`untrusted`；推导失效分支标注 untrusted。
- `tests/test_contracts.py` **11 passed**、`tests/test_policy.py`/`tests/test_contract_upgrade.py` **52 passed**、`tests/test_installed_wheel.py`/`test_cli.py`/`test_invoke.py`/`test_workflow.py` **71 passed**、`tests/test_plugin_runtime.py` **37 passed**（逐文件定向）。
- `scripts/compliance_gate.py`：**13/13 ok**，证据重生成（新合同 digest `sha256:49a775cf1bc202e22776d7d8b69904edbddf449d232b7a9649e72a21da2e113a`）。
- 按用户约束未跑全量 pytest；`platform_compatibility`/`latex_toolchain` 标记维持默认关闭。

## 3. R1 并发协调事件（同窗口并行批次）

本批次执行期间（11:39–11:43），另一会话将 `company.plan` 能力（6 工具）落入合同与 `packages/company-agent-plan`，且未同步其测试钉——正是 P0 记录第 2 节新增流程规则预言的失效模式。本次捕获并补齐的钉：

- `tests/test_contracts.py`：能力集 +`company.plan`；policy 键集 +4 个 `plan_write_*`；注册一次测试的 `capabilities_by_package` +`"plan"`。
- `tests/test_receipts.py`：lab ask 批准清单 +`company_plan_issue_create`/`company_plan_note_create`（现 13 项，为下达时的契约事实）。
- `tests/test_installed_wheel.py`：wheel 工具 `46 1`、能力 `11`。
- `tests/test_cli.py`：`tools` 目录 46 项、末位 `company_plan_note_create`。
- `tests/test_plugin_runtime.py`：能力计数 11；schema 一致测试的注册范围 +`company.plan`；依赖图期望 +`plan`（company-agent profile）。

残留待并行批次自己补的：`tests/test_plugin_policy.py`/latex 相关在全部 Alex 批次场景的覆盖（本轮定向未触发失败）。

## 5. 边界与下一步

- 本批次**未实现**：租户注册表、逐用户服务开通、真实 IdP、桌面/网页宿主把认证后主体写入 `COMPANY_AGENT_SUBJECT` 的接线。这些是 P1 余下工作，等待身份 Owner 输入。
- 主体绑定不变量已固化为合规门禁场景：见[P1-B 批次记录](company-agent-plan-p1-step2-2026-10-26.zh-CN.md)。固化首跑还暴露并用合同修复了 `subject_source` 的 `maxLength` 不足问题（`untrusted`=9 字符 > 8），说明持续门禁确有必要。
- 主体值仍是"归属标识，不是凭据"：不发送、不进遥测、不参与授权判定；授权仍由 `contracts/policy.json` 与平台 provider 决定。
- 隐私：`COMPANY_AGENT_SUBJECT` 只写入本地 JSONL 回执与 `company_capabilities`；不入 stderr 诊断（字段白名单未变）、不入模型上下文。
