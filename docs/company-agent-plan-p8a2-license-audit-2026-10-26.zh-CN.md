# P8 批次 A2 执行记录：供应链许可登记与审计门禁（2026-10-26）

依据：[约 2000 人天计划](company-agent-2000-person-days-development-plan-v1.0.zh-CN.md) P8「开源许可与第三方组件合规评审：ELv2/AGPL/品牌限制等逐项登记」（P2/P7 观测选型 H55 的登记口径承接）。本批次按「逐项登记，不整仓默认采用」落地机器可读登记 + 失效闭合审计脚本 + 持续门禁场景。

## 1. 交付

1. **登记文件 `docs/licenses-register.json`**（11 行组件）：`deepseek_harness`/`dsh_subagent_codex`（公司内部条款、品牌限制按内规）、`openai_codex`（上游声明 Apache-2.0，仅包装内运行）、`dsh_node`/`pnpm`（MIT）、`provider_protocol`（合同字符串钉，登记以闭合覆盖核验）、`jsdom`/`pytest`/`ruff`/`build`（MIT）与 `hypothesis`（MPL-2.0，仅工具链）。策略黑名单家庭：AGPL 家族（1.0/3.0、only/or-later）、SSPL、Elastic-License-2.0。
2. **审计脚本 `scripts/license_audit.py`（离线、失效闭合）**：
   - 登记行 schema 严格（8 项键恰集、5 项必填、scope 三值枚举、名称 ascii 唯一、版本/许可证/来源非空）。
   - **禁止许可证家族**：审计强制 `模块级普世底线 ∪ 登记政策清单`——登记清单自己删掉某条被禁家庭不能绕过普世底线（测试钉 SSPL 双许可证与 ELv2 两条）。
   - **覆盖核验**：workspace 的全部 `packages/*/apps/*/tests/ui` manifest 直依赖（workspace:href 协议项与 `@unitqc/*` 内部映射豁免）+ `pyproject` 的 `dev = [...]` 全卸出（单行/多行数组均可解析）+ `pins.json` 的全部钉组件——任一缺失即 `unregistered direct dependencies` 失败。
3. **持续门禁**：`normal / license-register-covers-direct-dependencies`（23 → **24**）：审计 `audit(ROOT)` 必须 ok、组件数 ≥ 必需覆盖数、至少含有 production_runtime/toolchain 两个 scope。`docs/evidence/compliance-local.json` 重生成 24/24 ok。

## 2. 验证

- `tests/test_license_audit.py` **6 项**：真仓审计通过（必需集 11 项含 python dev 工具链、三 scope 集合钉）、缺失覆盖（jsdom 摘除）失败、三类禁用许可证逐一失败、schema 漂移四件套（多余键/未知顶层键/坏版本/重复名字）失败。
- ruff 全部触碰文件干净；合同文件集合未变（登记放 docs/，不扩大 invoke 合同 digest）。

## 3. 边界（诚实的不完整）

- **传递依赖树逐包锁定**不在本审计内：安装树由 release manifest 的不可变摘要覆盖，逐包传递锁审计列为本批次的后继（计划 P8 内）。
- 公司内部包的许可证按内规登记（proprietary/内部登记()), 不含对外再分发条款的核证；品牌限制遵守条目已注明。
- `,` 依赖退役流程（PIP/JS 双生态 METADATA/SBOM 对接）待 P9 发布文档批次统一。
