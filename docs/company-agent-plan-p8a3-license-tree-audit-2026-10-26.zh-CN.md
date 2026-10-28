# P8 批次 A3 执行记录：安装树逐包许可扫描（2026-10-26）

依据：[约 2000 人天计划](company-agent-2000-person-days-development-plan-v1.0.zh-CN.md) P8 供应链评审的后继切片；承接 [P8-A1](company-agent-plan-p8a1-governance-boundary-2026-10-26.zh-CN.md)、[P8-A2](company-agent-plan-p8a2-license-audit-2026-10-26.zh-CN.md)（登记 + 直依赖覆盖）。P8-A2 留下的「传递依赖逐包锁定」由本批次以**安装树逐包许可扫描**落地：不联网、不调包管理器，直接读已安装树的真实清单。

## 1. 交付

`scripts/license_tree_audit.py`（离线、失效闭合）：

- **包根判定**：只有目录结构 `node_modules/<name>` 或 `node_modules/@scope/<name>` 下的 `package.json` 参与扫描——嵌入型裸 json（如 zod 自带的 `locales/package.json` 空身份清单）不算注册包，避免把内嵌代码 blob 误判为依赖。
- **身份校验**：`name`（npm scope 形态）与 `version` 形态失效闭合；manifest 尺寸 \(\le 262144\) 字节、树内包数 \(\le 4096\) 预算。
- **许可判定**：字符串/列表/`{"type":[...]}` 三种 npm 约定都归一化；禁用家族（普世底线 ∪ 登记策略，同 P8-A2 合并口径）逐包命中即拒绝；**内部行豁免**——`@unitqc/*` 与 `@deepseek-ai/*` 包允许省略 license 字段（条款在登记行），省略许可的外部包一律失败（`UNLICENSED` 声明的内部行也走豁免）。
- 按树汇总：本仓三类树（company-agent 39 包/7 内部豁免、minimal 6 包/6 豁免、tests-ui 39 包/0 豁免，共 84 包）的许可家族计数（MIT 62、Apache-2.0 3、ISC 2、BSD-2/3、MIT-0 各 1——无 AGPL/SSPL/Elastic 家族）。

## 2. 持续门禁

`normal / license-tree-scan-no-forbidden-family`（24 → **25**）：真仓安装树扫描必须 ok、扫描数 \(\ge 50\)、且许可家族集合对全部被禁家族零命中（黑名单取自许可登记的合并底线）。`docs/evidence/compliance-local.json` 重生成 25/25 ok。

## 3. 验证（不含全量，按工作方式约束）

- `tests/test_license_tree_audit.py` **6 项**：真仓扫描全绿（内部行计数与 ui 树非内部断言）、嵌套裸清单不算包根、内部行省略许可/外部行省略许可失败、禁用家族失败、缺席树容错（`packages=0`）。
- 复跑 `tests/test_license_audit.py`（P8-A2 直依赖审计）全绿；ruff 全部触碰文件干净；合同文件集合未变（审计为 docs/ + scripts/，不进 invoke 合同 digest）。

## 4. 边界（诚实的不完整）

- 许可字段的解析覆盖 npm 三种约定（str/list/type-list），但没有对 `/// 或 attr during` 的深度语义做解释器级别审读——家族黑名单按子串匹配；发现的新许可写法（如自定义文件引用）会按「未识别许可」如实计数并在审计报告可见。
- 安装树内容仍由 release manifest 的不可变摘要背书；本审计是**语义层**（许可），不重复完整性层。
- PNPM 平台摘要/锁文件本身（`.pnpm` 目录之外的 lock 元数据）未参与——按包清单已是安装事实，锁文件审计无所需。
