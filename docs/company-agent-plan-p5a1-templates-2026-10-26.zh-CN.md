# P4→P5 批次：模板扩展（量化统计与 shots 交付绘图）（2026-10-26）

依据：[约 2000 人天计划](company-agent-2000-person-days-development-plan-v1.0.zh-CN.md) P5「在已落地两个模板基础上扩展统计、绘图、报告和 Canvas 模板」工作包的首切片。前置批次：[P4-a1 窄链重验与接缝登记](company-agent-plan-p4a1-seam-recert-2026-10-26.zh-CN.md)（7/7 门绿，P4 剩余面登记为平台 Owner 依赖后放行 P5 内核工作）。

## 1. 交付

`contracts/templates.json` 由两个模板扩展到 **四个**（`catalog.load_templates` 字面量钉同步扩）：

1. **`metric-quantiles`**（统计+绘图）：`metrics_table` 输入与 `metric-summary` 同型；输出在既有 audit 形状内（`min_value/max_value/units/reasons` 恒定），每单位派生**命名顺序统计条形图**——`min/q25/median/q75/max`，分位取下位序（`ordered[floor(p·(n-1))]`，确定性、无外部依赖）；表头语义审计完全复用（`invalid_unit/range_violation/duplicate_name/empty/chart_budget`）。单元数超过 8 时按 `chart_budget` 失效闭合（图不画、状态标 flagged）；表格被标记时一根图都不画（延续「被标记的表格不能渲染误导数字」的教师则）。
2. **`shots-chart`**（交付绘图）：`shots_delivery` 输入与 `shots-audit` 同型（`requested/actual` 合同边界不变）；**即使被标记也画出 requested/actual 差值条形图**——这是有意的一条例外并有注释说明：交付计数差是被审计事实的可视化本身，画出来恰恰是诚实呈现（指标表格那条「flagged 不作图」教师则专门保护的是概率/计数语义数字，此处不冲突）。结构级畸形照旧失败闭合。

合同其余不变：`company_analysis_render` 输出 schema 零改动（audit 的 min/max、charts 的 bar 描述子全部既有键）；`sources` 全部指向既有工具名；可见性沿用 `company_analysis_render` 全 preset。

## 2. 验证（不含全量，按工作方式约束）

- `tests/test_analysis.py` 12 → **18 项**：四模板合同清单钉、10 值分布的五分位数精确值（q25/q75 位次钉）、单值退化与空表、flagged 不作图、12 单位 chart_budget 失效闭合、非数值短路失败闭合（`finite number` 一致短路贯穿四模板，`_semantic_audit` 同时给所有模板加上值类型/有限性短路——material-summary 同步受益）、shots-chart 差值绘图（flagged 与 complete 两种）、结构失败闭合。
- 关联面：`test_contract_upgrade/test_catalog/test_compliance_report/test_knowledge_quality` **62 passed**；合规门禁重生成 **22/22 ok**；`tests/ui` node **31/31**；ruff 全部触碰文件干净。

## 3. 边界（诚实的不完整）

- 分位数取**下位序统计**（非插值）：对 HDR 中文结果表是确定性选择，Canvas 渲染按长度排序后的描述子取值即可；「报告/Canvas 模板」的更大词汇表（表格倒数、对比快照 delta）需要新的 reasons 词汇与本批次不同的审计形状，留待 P5 后续切片。
- `metric-quantiles` 只对完整表格作图；`duplicate_name`/范围违例等域级发现依旧只标注不渲染。
- C 端可观测（绘图描述子在工作台三栏的落点）属 P6 计划范围。
