# LaTeX 工具链阶段 0：黄金矩阵与 Overleaf 兼容性门禁

日期：2026-10-26  
状态：阶段 0 实验设施已建立并在本机跑通 5/6；未修改产品合同。  
背景：中栏 LaTeX 工作区方案要求"语法完全相同、排版尽量一致"。只有先证明一条固定编译链能复现目标环境，`company.latex` 合同才有可靠基础，因此本阶段先做编译行为验证，不接入 Agent、不修改 `contracts/`、不新增运行时循环。

## 一、承诺分层

- **源码语法**：编辑器与 Agent 都只编辑原始 `.tex/.bib/.cls/.sty` 文本；本矩阵证明工程在固定链路下编译成功且黄金源文件保持位字面不变（task 目录只拷贝、不改写）。
- **编译行为**：同一 TeX Live 版本 + 同一编译器 + 同一宏包/字体/run 配置之下，页数、文本与引用应可复现；黄金矩阵把"项目级编译器和 TeX Live 版本"记录进清单，禁止用"最新版"隐式替换。
- **PDF 二进制**：不承诺逐字节相同（元数据与时间戳允许差异）；比较维度是页数、pdftotext 文本与参考差异。

## 二、本机工具链真值（2026-10-26）

| 组件 | 状态 |
| --- | --- |
| pdflatex / xelatex / lualatex | 可用，TeX Live 2023.25（Debian） |
| bibtex / makeindex | 可用 |
| pdftotext 文本校验 | 可用 |
| ctex + Fandol 中文字体 | 可用 |
| biblatex + biber | 不可用（未安装） |
| latexmk | 不可用（矩阵直驱引擎，不依赖） |
| Docker / 沙箱镜像 | 不可用（当前环境） |

矩阵不预装任何系统组件；缺失项如实进入结果（fail-closed），安装后门禁自动转绿。

## 三、黄金项目集（tests/latex/golden/）

| 项目 | 编译器 | 后端 | 目的 |
| --- | --- | --- | --- |
| g01-pdflatex-basic | pdflatex | 无 | 章节、交叉引用、公式、booktabs 表 |
| g02-xelatex-chinese | xelatex | 无 | ctex + Fandol 中文，中英混排公式 |
| g03-bibtex-classic | pdflatex | bibtex | 经典 BibTeX 两轮引用解析 |
| g04-biber-biblatex | pdflatex | biber | biblatex/biber；当前诚实未配置 |
| g05-tikz-pgfplots | pdflatex | 无 | TikZ + PGFPlots 内联图形 |
| g06-multifile-layout | pdflatex | 无 | 多文件平铺布局（禁止改写布局） |

每个项目一个 `project.json` 清单：`{id, compiler, main, backend, packages, contains, pages_min, purpose, description}`，由 `scripts/latex_golden_matrix.py` 校验并执行。

## 四、运行方式

```bash
# 1) 工具链真值（JSON）
python3 scripts/latex_golden_matrix.py --detect
# 2) 完整矩阵 + 落盘证据
python3 scripts/latex_golden_matrix.py --gate --output docs/evidence/latex-matrix/<日期>-<标识>.json
# 3) 结构门禁（默认必跑，不需要 TeX）
python3 -m pytest -q tests/test_latex_matrix.py
# 4) 工具链门禁（显式 opt-in；装齐组件后应转绿）
python3 -m pytest -q -m latex_toolchain tests/test_latex_matrix.py
```

退出码：0 全部通过；1 有项目编译/内容/对照失败；2 工具链不完整或存在未配置项目（`--skip-unconfigured` 可放宽后者）。

## 五、门禁接线

- 默认验收范围（`pyproject.toml` addopts 与 `scripts/acceptance_pytest.py`）同时剔除 `platform_compatibility` 与 `latex_toolchain` 两个 opt-in 标记；结构门禁永远在默认范围执行。
- `scripts/verify_acceptance.py` 的证据身份字段同步列举两个被剔除标记；`tests/test_acceptance.py` 对该形状钉桩。
- 黄金源文件禁止出现 `\write18`、`shell-escape` 请求；矩阵调用引擎固定加 `-no-shell-escape`。

## 六、Overleaf 参考对照（parity）

在 `tests/latex/references/<golden-id>/`（已 gitignore，规范见该目录 README）放置：

- `reference.pdf`：Overleaf 导出的原文 PDF。
- `meta.json`：恰好 `{"compiler", "texlive", "pages"}`；`compiler` 必须与清单一致。

矩阵在参考存在时自动比较：编译器一致、页数须相等（失配即失败）；`pdftotext` 可用时比较归一化文本词重合率（阈值 0.9），否则标注 `match_text_unchecked`。

## 七、验收条件与当前状态

1. 源码原样导入、矩阵不改写工程：达成（copytree 原样拷贝）。
2. 编译器与 TeX Live 版本可复现：达成（清单显式记录，本机三项目 5/6 通过）。
3. 页数一致：黄金自查达成；Overleaf parity 待参考件。
4. 页面尺寸/几何一致：未实现（后续用 pdfinfo/页面截图扩展）。
5. 文本与引用一致：达成（pdftotext 文本校验通过，含中文）。
6. SyncTeX 双向定位：未实现（编排进中间栏阶段）。
7. 不兼容诚实失败：达成（g04 未配置即整门禁 exit 2，pytest opt-in 同样失败并给出安装提示）。

本机首轮证据：`docs/evidence/latex-matrix/2026-10-26-local-matrix.json`（success=5，unconfigured_project=1，failure=0）。

## 八、下一步

1. 补齐组件使 6/6 全绿：`sudo apt-get install latexmk biber texlive-bibtex-extra`（或 `tlmgr usermode` 装列）。
2. 按 references/README 导出 1–2 个真实 Overleaf 项目放入参考目录，运行矩阵取得第一份 parity 结论。
3. 阶段 1 按开发顺序先改合同：新增 `company.latex` capability 与 `company_latex_structure/read/edit/batch_edit/check/compile/diff/checkpoint/revert/sync` 的输入输出 schema、结果预算与审批策略；随后再写 Python adapter、DSH 插件与测试。

## 九、未完成边界

未部署沙箱编译镜像（无 Docker）；未实现 SyncTeX、视觉对照与队列化编译；未接入 Agent 工具或中栏工作区；本记录的浏览器/多用户验收在阶段 4–6。
