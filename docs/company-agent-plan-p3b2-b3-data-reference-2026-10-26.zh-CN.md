# P3 批次 B2 + B3 执行记录：受管数据处理与工作区文件引用（2026-10-26）

依据：[约 2000 人天计划](company-agent-2000-person-days-development-plan-v1.0.zh-CN.md) P3「通用办公、文档、数据处理和项目协作插件」与「会话、消息、文件引用、历史、任务拆分和工作区上下文」两个工作包的内核切片。本批次新增两个本地工具（合同先行），均无句柄、无 provider 外呼、结果有界。

## 1. B2：`company_table_profile`（数据处理）

- 输入：操作员提供的 CSV 快照（\(\le 6000\) 字节、可选 delimiter \(\in\)`{, ; | ⌉}`）；输出：行数（\(\le 64\)）、`columns`（列名、numeric/text 类型、complete 标记，\(\le 16\) 列）、`numeric`（每数值列 count/min/max/mean，全部有限数）、`integrity`（`row_budget/column_budget/cell_budget/column_mismatch/duplicate_header` 五类原因）。
- 语义钉：列在被确定为文本、空单元格、重复表头或表头仅行的情况下都确定性地判为 `text`；numeric 列要求**每一数据行都有非空在预算内单元格**且全体有限；数据质量问题以 `integrity.reasons` 标记而非报错，参数级失败（空表、超预算、未知分隔符、空表头、未知名字节）失败闭合。
- 输入快照永远按数据对待；无执行、无外呼（survey H40/H23 反例的对应设计）。
- 挂 `company.workflow` 能力（operation `table.profile`），boot/lab/algo 可见、sign 不可见；终止预算自动记账。

## 2. B3：`company_workspace_reference`（文件引用与 H39 反例的对应物）

- 输入：工作区相对 POSIX 路径（仅一处文件）；挂载根来自 `COMPANY_AGENT_TOOL_WORKSPACE`（DSH runtime 已有合同 env）。输出：`sha256/bytes/lines/kind(text|binary)/truncated/trust(untrusted_reference_data)`，**只回元数据，绝不返回文件正文**。
- 硬边界：无根、绝对路径、`..`、反斜杠、双斜杠、缺失目标、目录目标一律失败闭合；symlink 解析后仍必须落在解析后的挂载根内（逃逸拒绝）；\(\le 2\mathrm{MB}\) 全量摘要（`sha256`+`lines`），更大文件 `truncated=true`、`sha256` 空串、按后缀/嗅探类别，行数计数照算（行计数对超大文本有界循环）。
- 挂 `company.workflow`（operation `workspace.reference`），可见性与预算同 B2。这条绑定是「显式读取路径 + 字节预算 + 未完整状态显式标记」的数据引用基础，后续 P5 的大资产分页/摘要批次在其上扩展。

## 3. 验证

- `tests/test_table_profile.py` **9 项**、`tests/test_workspace_reference.py` **8 项**：形状锁、分隔符、行/列/单元格预算、混合与空值语义、重复表头、表头仅行、参数失败闭合、sign 可见性拒绝、预算计数联动、逃逸/缺失/目录拒绝、二进制分类、超大文件部分绑定。共享计数钉随之更新到 52 工具状态（CLI、installed_wheel `52 1`、DSH lab 探针 60、boot 探针 8——boot 现含 7 合同工具）。
- 合同工具数 50 → **52**（完整目录末位仍是 `company_plan_milestone_create`）；`docs/evidence/compliance-local.json` 重生成 19/19 ok，合同 digest `06a4f0c9…`。

## 4. 边界

- 「通用办公、文档转换」（Office/OpenDocument/PDF 读写）没有被打开：文档能力继续由 latex 工作区与知识登记承担，办公插件等待真实试点需求用例再单独立批。
- `company_workspace_reference` 只读元数据；**读取正文**能力仍属 DSH 原生 read（有字节预算），本批次不复制它的职责。
- 包 1 的会话/历史/任务拆分主体在 DSH 运行时（唯一 runtime），内核侧不再卷入。
