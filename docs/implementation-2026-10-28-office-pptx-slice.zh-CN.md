# WPS 套件移植 · office.pptx 生成与文本回写切片(2026-10-28)

对应清单:`C:\Users\Administrator\Downloads\WPS-SUITE-PORTING.md` §4.5(L3 pptx:结构化布局生成 + shape 文本回写,并在 2026-10-29 补上 §4.1 officecli 视觉预览)。与并行会话(批次 1-3 与品牌擦洗、其下一站是 P5 交付)不重叠。

## 现状前提

- 接上一会话的 audit 切片(office 8 工具);本切片追加 **`company_office_pptx`**(`office.pptx`,写入工具),office 工具 8→9、合同全量 65→66;boot/lab/algo 可见,sign 保持 office-free。

## 实现

- 合同:`scripts/_wps_port_pptx_slice.py` 一次性补丁(先断言缺席再插入,tools.json office 块接在 audit 之后、capability 追加、三个固定 preset 在 audit 后可见);补丁已执行,脚本与落库 JSON 逐字一致(description/parameters/output 重建比对全相等)。
- 适配器:`src/company_agent/office_pptx.py`,纯标准库(zip + ET):
  - **render**:从 slides 数组生成 .pptx,每张为结构化版式——title(标题+可选副标题)、agenda(自动 1..n 编号)、bullets(• 项目符号)、two_column(双栏)、matrix(真 PowerPoint 表格对象 a:tbl,1..6×6 单元格,ragged 拒绝)、checklist(□ 前缀);固定 16:9 几何(12192000×6858000 EMU),命名文本框 + 极小合法母版/版式/主题包,WPS/PowerPoint 可打开编辑大纲。
  - **edit**:按 `slide`/`shape`(1..N,`p:sp` 文本框文档序,表格不算)重写可见文本,继承原首 run 的 rPr;**整批先验后写**,任一目标不存在 → 全批拒绝,绝不"跳过单条";换行拒绝(一个 shape 一段)。
  - **B5 回放闸门**:写回包重新打开,逐张 `a:t` 序列与生成计划比对;edit 复核失败时**恢复原始字节**再抛错;render 复核失败则如实宣"该产物不可交付"。
  - 上限即拒绝:64 张、每 shape 4000 字、每栏/列表 8 行、标题 120 字、单元 120 字、矩阵 6×6;20MB 上限与损坏包拒收对应摄取口径;写盘复用 `office_create` 的 P0 围栏与原子 temp+replace(office_chart 同款复用)。
  - 确定性:zip 条目时间戳固定为 1980-01-01,同内容两次 render 的 sha256/bytes 相等(有测试)。
- 接线:`catalog.py` 期望名单、`invoke.py` 派发、`packages/company-agent-office/src/index.js` 注释。

## 2026-10-29 补充:preview(§4.1 officecli 视觉预览)

`action=preview` 补齐参考实现 §4.1 的 pptx 视觉预览面(page count → shape 枚举 → 按页截图),行为逐条对清单:

- **二进制解析**:顺序与参考一致——`COMPANY_AGENT_OFFICECLI`(绝对路径,须是文件)→ PATH 上 `officecli`(`shutil.which`)→ 都没有则如实拒绝(`不出替身`)。vendoring 脚本本身不进本仓库(参考仓库的 DLL/RLS 同款留待分发渠道)。
- **三次受限子进程**:命令形状与 §4.1 表格逐字对应——`view <file> stats --json`、`query <file> shape --json`(条目按 `/slide[i]` 路径解析)、`view <file> screenshot --page N -o <workspace> --screenshot-width 1280 --screenshot-height 720 --render html`;子进程规格与 soffice 转换器同款(数组化 argv、`office_convert._minimal_env` 白名单 env、stdout 4MB 截断、180s 超时),三次运行共用**按文件的 officecli 租约**(复用 `office_convert._lease`,对应清单第 10 条「officecli 不能并发抢同一文件」),cwd 落在一次性 tempdir,不污染 workspace。
- **双口径交叉校验(B5 思路)**:officecli 报的页数与重开包的幻灯片数必须一致;`query shape` 的总文本框数与逐张分布必须与包内 `p:sp` 枚举一致(即 edit 寻址的 1-based slide/shape 文档序)——两处不一致即整次拒绝,回执里的 shapes_detail 就地复用与 edit 完全一致的寻址。200 文本框、64 页超出即拒绝(上限即拒绝,不截断)。
- **截图落点名与刷新**:`<project>/preview/<stem>/slide-N.png`(与合同描述一致);每页产物必须非空且带 PNG magic,否则拒绝;重跑同文件时同名覆盖、页数缩减后删除 `slide-<k>.png` 旧页,用户其他文件一律不动;--overwrite 参数对 preview 拒绝(与 edit 同规)。
- **并发窗口闸门**:收尾重读源文件字节,与开头快照不等(运行期间被并发改写)则整次拒绝,绝不描述一个已不存在的 deck。
- **回执预算闸门**:本地工具回执 64KB 上限(`contracts/results.json`),`shapes_detail` 每条裁 200 字后按 UTF-8 字节估算,超过 `DETAIL_BUDGET = 48_000` 在写任何截图前拒绝(CJK 文本 3 字节/字,字符数口径会漏——与 `validate_result_size` 字节口径对齐)。
- 合同:description/schema(`screenshots`/`shapes_detail`/`officecli` 字段)维持 2026-10-28 补丁原样,适配器实现与合同逐字对上;`test_plugin_runtime` 计数位不变(不加工具)。

### 门禁结果(2026-10-29 补充)

- `tests/test_office_pptx.py` 17/17:新增 9 例——happy path(6 页/12 文本框/6 张 PNG 落盘/sha256 与磁盘一致/shapes_detail 首末条对上 `company_office_analyze` 同款 a:t 口径)、旧页清理、动作纯度与 overwrite/后缀/缺文件拒绝(桥前拒绝,零 artifact)、无 officecli 如实拒绝、页数不一致/枚举不一致/非法 JSON/坏 PNG 拒绝、65 页与 201 文本框上限在桥前拒绝(stub 断言二进制未运行)、回执预算拒绝、运行中被改写拒绝。
- stub 以包内真实字节当 oracle(页数/文本框数从 deck 重新推导),不依赖二进制;stub 若在门禁后越权运行测试会显式失败。

## 门禁结果

- `tests/test_office_pptx.py`(2026-10-28 首批)8/8:六张混合版式 + 用 `company_office_analyze` 当 oracle 的落盘交叉验证(pptx 文本抽取逐张对上)、确定性字节、覆盖拒绝/与 overwrite 重写、上限与形状拒绝(kind/matrix 行列/行数/空标题)、edit 回写 + oracle 复读、坏目标整批拒绝且字节不变、动作纯度(content/edits 交叉拒绝)、overwrite=true 拒绝、后缀拒绝。
- `test_office_audit` 11/11 保持;`tests/test_contracts.py` 与 `test_no_legacy` 上限断言通过;`tests/test_plugin_runtime.py` 37/37(工具总量 59→65→66 计数与 boot 期望列表同步维护:`test_core_runtime_reads_python_contract_catalog` 与 `test_core_runtime_filters_registered_catalog_by_preset`;这两处自批次 3 起就是"各批追加工具后必须同步"的门禁位,并行会话下一批工具落地时同样要 +1)。
- Lint:按机器 E902 的 stdin 通道(见 audit 切片记录),`office_pptx.py`/`tests/test_office_pptx.py`/`_wps_port_pptx_slice.py`/`catalog.py`/`invoke.py` 全部 0 违规。

## 未动/留给后续

- P5 交付(命名/落点/export PDF/.doc→.docx)、P6 `open_in_wps`、`run_compute` 沙箱、OCR:留待并行会话的批次节奏(pptx 视觉预览与截图已于 2026-10-29 由本切片补齐);本切片未涉及。
- `edit` 对表格单元格文本不支持(表格是 graphicFrame,不是文本框):合同描述已如实写明,后续若需表格单元格改写,走重新 render 或单列后续工具,不在本切片扩表。
- 全仓 pytest 门禁里与本切片无关的遗留失败(2026-10-29 记录):`test_cli` 两例仍在断言 65 个工具(合同已到 70,属于追加 compute/deliver/open 工具的并行切片的计数同步位);`test_bridge_behavior`/`test_cloud`/`test_dsh_lifecycle` 的 DSH 子进程组失败与 `test_plugin_package` 的 npm 构建属运行环境,`test_overleaf_*` 为外网传输门禁。office 各门禁 75/75 全绿。
