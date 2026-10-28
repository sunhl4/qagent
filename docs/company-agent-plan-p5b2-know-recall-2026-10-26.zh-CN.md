# P5 批次 B2 执行记录：知识检索治理四维硬化与评测（2026-10-26）

依据：[约 2000 人天计划](company-agent-2000-person-days-development-plan-v1.0.zh-CN.md) P5「知识登记治理硬化与检索评测：撤权即时性、时效、多租户与摘要漂移」工作包。前置登记：[P5-A1 模板扩展](company-agent-plan-p5a1-templates-2026-10-26.zh-CN.md)。本批次内核**零改动**（既有准入门语义已经正确），工作落在**把四个治理维度钉进回归与持续门禁**，消除了「语义存在但无证明」的空窗。

## 1. 缺口盘点与交付

既有事实：`knowledge.search` 每次调用重读注册表（无缓存），准入门覆盖 revoked/unapproved/expired/stale_hash/audience_filtered/unregistered/registry_invalid 七类原因。缺口是这四个维度的**测试钉与持续门禁**各有残留：

1. **撤权即时性**：无测试确认「同进程两次 search 之间改写注册表」会即时生效（这正是"无缓存"的证明）。新钉 `test_revocation_is_immediate_to_the_next_search`：命中 → 改写 revoked → 立即命中消失（`revoked` 原因）→ 恢复后立即恢复。既证即时性也证无隐藏缓存态。
2. **时效边界**：无测试钉"过期的精确拍点"。新钉 `test_expiry_boundary_is_the_exact_epoch`：时间冻结在 `expires_epoch` 前两秒可见、**恰好等于**登记时效仍可见（实现是 `time > expires` 严格大于）、下一秒即 `expired`。
3. **多租户/多根隔离**：无测试确认多根之间"同名单文件、各自 registry 与受众"互不污染。新钉 `test_multi_root_isolation`：`builtin` 与 `configured-1` 两根各自命中同一 stem 的文档（按 root 身份区分），撤销 builtin 根后仅 builtin 的 `revoked` 生效，configured-1 继续服务；`sign`（外部受众）同时收到 builtin `revoked` + configured-1 `audience_filtered`，内部行绝不泄露。
4. **漂移恢复**：漂移侧只有"改文件不重批 → `stale_hash`"的钉，缺恢复链。新钉 `test_drift_serializing_round_trip`：改字节 → 不服务（stale_hash）→ 以新 sha 重批 → 立即恢复可查。

## 2. 持续门禁

`scripts/compliance_gate.py` 新增 `normal / knowledge-recall-immediacy`（22 → **23**）：在 store 目录用 scratch 语料 + 注册表打电话，命中 → 撤权行写入 → 下一次 invoke 必须零 hits 且 `reasons=["revoked"]`。`docs/evidence/compliance-local.json` 重生成 23/23 ok。

## 3. 验证（不含全量，按工作方式约束）

- `tests/test_knowledge_recall.py` 新增 **4 项**全绿；复跑 `tests/test_knowledge_registry.py`（既有治理钉）同绿；ruff 触碰文件全部干净。
- 评测脚本 `scripts/evaluate_knowledge.py` 的排名/召回口径不变；治理维度是门禁承载而非模型判分。

## 4. 边界（诚实的不完整）

- 受众维度保持**按 preset（public/internal）**：subject 级受众（把 knowledge 受众挂到 tenant 注册表行）需要登记合同扩列（`audience_for_subject` 词汇），属 P1 后续与tenants Owner 的范围，本批次不动。
- 多根隔离钉只覆盖双根；root 语义中 `configured-N` 的排序/fan-out 行为由 roots() 的既有测试承载。
- 评测输出的治理段落未进 `evaluate_knowledge.py` 报告（治理即门禁已足），保持评测器为排名/召回单一职责。
