# C-01ab · 助手回答读成科学纸

| 状态 | 完成 · 只动 `app.css`。栏宽 72ch、标题上留白、书板式表格（表头墨色不金）、块级公式留白、电路图随纸配图注、代码等宽浅底。结构一行不动。**不算 G0**。**未 commit** |
| --- | --- |

## 为什么

形态讨论（2026-08-29，见 `qagent-chat-or-not` 画布）定死：Qagent 是仪器上的对话，聊天保留。要改的是回答的阅读质量——公式、表、电路图读成印在纸上的科学回答，不是挤在聊天气泡里的富文本。这是执行计划（`qagent-face-execution-plan`）的第一刀。

## 改了什么（全部在 `apps/customer-shell/app.css`）

- 新增 `--mono` 令牌；`code` 用等宽 + `panel-2` 浅底 + 细边，不金不蓝。
- `.msg.assistant .msg-body` 栏宽 72ch；`.msg.assistant` 行高 1.75、内边距加大。
- 段落/列表下距 14px；h3/h4/h5 上留白 20px，首个标题不顶；h3 衬线 19px。
- 表格书板式：上下 2px 粗线（`line-strong`）、表头下 1px 细线、无竖线；`thead th` 墨色 650，不再金。金只留给许可与封条（C-01ac 完成另一半）。
- `.math-block` 上下 20px 留白、可横滚；`.katex-display` 内边距收窄，居中由 KaTeX 默认。
- `.circuit-face` 去面板化：透明底、上下细线、直角，像论文里的图；`.circuit-cap` 图注字距 0.08em。「下载这份线路」不动。

## 没动什么

- `app.js` 结构一行不动：`fillRichText` 仍不 innerHTML 整段；`renderMath` / `splitMath` / `takeDisplayMath` 不动；批准块仍 `send("批准")` / `send("先不批")`，无 `assignmentAction`。
- 布局锁不动：`grid-row: 2 / 4`、`grid-row: 3`、`.welcome .packs` 隐藏、`--radius` / `--shadow` / `--gold-dim`。
- 无 `ionstack_twin_run`、无 `twin_id=`、无 `a2_chem_pes`、无房间/墙词。
- 用户轮次、故障条、许可单、浅纸翻转：都不在本波，分别在 C-01ad / C-01ac / 后续单列。

## 验证

- `tests/test_c01ab.py` 七项全绿，已挂 `run_tests.py`。
- 回归：`test_c01z`（KaTeX）、`test_c01aa`（连线+锁）、`test_c01y`、`test_c01x`、`test_c01w` 全绿。
- 活验：重启 3080，发一句带公式的平常话，回答读成科学纸；电路图带图注。

**不算 G0**。未 commit。
