# WPS 套件移植 · office.audit 格式体检切片(2026-10-28)

对应清单:`C:\Users\Administrator\Downloads\WPS-SUITE-PORTING.md` §4.12(格式体检三口径)+ 附录 B 的「格式体检三口径」项。本切片与并行会话的批次 1-3(P0 基座 / P1 摄取 / P2 创建 / P3-P4.5 compare·edit·validate·chart·matter)不重叠:它补的是 L4 的配套"体检面",不触碰其余 office 模块。

## 现状前提

- 并行会话已完成批次 1-3 并正在修复三件套边界用例;`company.office` 此前为 7 工具(analyze/create/compare/edit/validate/chart/matter)。
- 本切片新增 **`company_office_audit`**(`office.audit`,只读),office 工具 7→8;boot/lab/algo 可见,sign 保持 office-free。

## 实现

- 合同:一次性补丁脚本 `scripts/_wps_port_audit_slice.py`(先断言缺席再插入,tools.json 接在 matter 之后、capability 列表追加、三个固定 preset 在 matter 后可见);补丁已执行,脚本文本与落库 JSON 逐字一致(经重建比对 description/parameters/output 全相等)。
- 适配器:`src/company_agent/office_audit.py`,纯标准库(zip + ET):
  - **baseline 口径**(= from-scratch 与 retemplate):GB/T 9704-2012 草案规则表——A4 页 + 37/35/28/26mm 边距(±1mm)、正文仿宋 16pt、26.5-30pt 行距带、首行缩进 2 字(±0.25)、标题小标宋 22pt 居中、一级/二级/三级标题黑体/楷体/仿宋;规则对象 `rule_set` 状态 **draft-pending-confirmation**,可整表替换。
  - **imported 口径**:不套模板,输出 bounded facts(页面/边距/docDefaults 默认字体字号/正文多数票字体·字号·行距·缩进/标题字体字号),只报结构性异常(多分节)。
  - 锚号复用 P1:`L{n}` = `word/document.xml` 的第 n 个 `w:p`(与 `company_office_analyze` / `office_validate` 逐字一致;有一个测试交叉验证含空段与表格段时与 analyze 的 items 编号对齐)。
  - 诚实边界:未知字体/字号/自动行距/首行缩进不可得 → 进 `unchecked`(不判违规);标题同样未知时进 `unchecked`;violation 聚合计数、首处定位(回执短);表内段落只计段号不判口径;5000 段上限超出如实 `truncated` 并在 `unchecked` 标注入尾段数;20MB 与损坏包拒收与摄取同口径;issue 128 条硬上限有截断标记。
- 接线:`catalog.py` 期望名单、`invoke.py` 派发、`packages/company-agent-office/src/index.js` 注释(注册走 capability 的 `registerCapabilityTools`,无需改插件逻辑)。

## 门禁结果

- `tests/test_office_audit.py` 11/11 通过(合规格文档通过 + 边距/标题/正文口径违规逐项 + 标题级字体计数 + 表格跳判与锚号交叉验证 + imported 与 baseline 同文件对照 + 多分节双口径 + 5001 段截断 + 后缀/损坏包拒收)。
- `tests/test_contracts.py` / `tests/test_policy.py` 通过;`tests/test_plugin_runtime.py`(52)+ `tests/test_verify_dsh_profiles.py` 全绿。
- 顺手修正两处**既有**过期断言(此前就红,与批次 1 时代一致):
  - `test_plugin_runtime::test_core_runtime_reads_python_contract_catalog` 的 lab 计数 59→65;
  - `test_plugin_runtime::test_core_runtime_filters_registered_catalog_by_preset` 的 boot 期望列表补齐批次 3 五个工具 + 本批 audit。
- Lint:ruff 的 `E902 stream did not contain valid UTF-8` 对**全库所有文件**(含 ascii-only 探针)报错,双环境(Windows anaconda ruff 0.15.12 与 WSL `~/.local/bin/ruff`)同现,且 ruff 的 stdin 通道正常——是本机文件读取路径坏了,不是代码问题。改为用 `--stdin-filename` 通道把本次新增/修改文件按 `pyproject.toml` 配置 lint:**三个新文件全部 0 违规**;`catalog.py`/`invoke.py` 0 违规。历史文件(office_ingest 1 处、office_matter 7 处等)的存量留给并行会话的批次修复。

## 未动/留给后续

- `test_no_legacy.py` 现有 2 个失败与本次无关:`docs/conversation-log-2026-10-26-to-28.zh-CN.md` 仍含旧项目指向串、根目录存在 `.gate-tmp/` 与 `wsl_pnpm_setup.sh`(均为更早状态遗留)。
- 移植清单中尚未实现、且与另一会话批次计划可能重叠的:P5 交付(命名/落点/导出)、`open_in_wps`(P6)、pptx 生成、run_compute 沙箱、OCR;本切片未涉及。
