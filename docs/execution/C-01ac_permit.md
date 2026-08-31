# C-01ac · 许可单：上机批准从气氛按钮变成互锁单

| 状态 | 完成 · `awaiting=approve` 贴独立许可单；`button.act` 默认墨色，金只在许可单与在办批准钮；封条文字本就由 `faceLabel` 承担。**不算 G0**。**未 commit** |
| --- | --- |

## 为什么

执行计划（`qagent-face-execution-plan`）第二刀。批准是互锁，不是聊天气氛：采购要看见「上我们的机器前有人拍板」是一个独立对象，不是气泡尾巴上的两个按钮。

## 改了什么

- `app.js` `addMessage` 批准块：包成 `section.permit`，标题「许可单」+ 说明「上我们的机器前要你拍板。估计写在右侧在办；不批不会上机。」按钮原文不动：`send("批准")` / `send("先不批")`，文案仍「批准上机 / 先不上机」。无 `assignmentAction`。
- 估计：`extras.pending.makespan_ns` 存在且为正才画「估计 · N ns」。当前 `_PENDING_FACE_KEYS`（`approval_id / rpc_id / tool / reason`）不带这个字段，所以现在不画——不编。字段哪天到了，脸自动画。
- `app.css`：新增 `.permit` 一族（金边、金题、说明、估计行）。`button.act` 默认改墨色（`elev` 底 + `line-strong` 边）；金只留在 `.permit button.act` 与 `.inbox-row button.act`（在办批准钮，C-01m 的 HTTP 批准）。发送与设置保存随之变墨色——发送不再是页面最大的黄块。
- 封条：核查确认 `face-seal` 圆点是 `aria-hidden` 纯装饰，「已签收」文字由 `faceLabel` 承担（C-01x 已有）。本波不加重复文字，只把这条锁进测。

## 没动什么

- 批准路径：`send("批准")` / `send("先不批")` 原文；在办 `assignmentAction(..., "approve")` HTTP 批准不动。
- 无 `ionstack_twin_run`、无 `twin_id=`、无 `a2_chem_pes`、无房间/墙词。布局锁（`grid-row`）、`--gold-dim`、`composer-kicker` 全留。
- 服务层一行不动：`_PENDING_FACE_KEYS` 不加字段。

## 验证

- `tests/test_c01ac.py` 七项全绿，已挂 `run_tests.py`。
- 回归：`test_c01aa`（批准块切分锁）、`test_c01z`、`test_c01y`、`test_c01x`、`test_c01w`、`test_i01l`、`test_h01l` 全绿。
- 活验：3080 静态逐请求读盘，刷新即见；待批准时回答末尾贴许可单。

**不算 G0**。未 commit。
