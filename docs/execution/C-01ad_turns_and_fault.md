# C-01ad · 用户轮次与故障条

| 状态 | 完成 · 只动 `app.css`。用户轮次保留对话位置（右侧、ion 边、无气泡）；故障条加「故障」文字标签；reduced-motion 停脉冲本就有，本波锁进测。**不算 G0**。**未 commit** |
| --- | --- |

## 为什么

执行计划第三刀。形态已定「仪器上的对话」：用户轮次不改成批注，仍是对话的一轮。要收的是两件小事——人说的话再安静一点；故障不再读成像模型在说话。

## 改了什么（全部在 `apps/customer-shell/app.css`）

- `.msg.user`：位置不动（`align-self: flex-end` + ion 右边线、无背景无阴影无圆角）。间距微调，硬编码 `#d5e4ef` 换成 `color-mix(in srgb, var(--ink) 88%, var(--ion))`。
- `.msg.fault .msg-body::before`：故障条上方加「故障」小字标签（红、字距 0.18em）。故障是纸外的一条系统状态，不是模型的一句话。`fillRichText` 清正文不影响 CSS 生成标签。
- reduced-motion 停脉冲：C-01aa 已有 `@media (prefers-reduced-motion: reduce)` 停 `.msg.busy` 脉冲，本波只把它锁进测，不改行为。

## 没动什么

- `app.js` 一行不动：`readJson` / `humanChatFault` / `misses >= 8` / 「这次没连上。再发一句即可。」全留。
- 许可单不动：`send("批准")` / `send("先不批")`、`section.permit`。
- 布局锁、禁词、三句柄全留。无 `ionstack_twin_run`、无 `twin_id=`、无 `a2_chem_pes`。

## 验证

- `tests/test_c01ad.py` 六项全绿，已挂 `run_tests.py`。
- 回归：`test_c01aa` / `test_c01z` / `test_c01y` / `test_c01ab` / `test_c01ac` / `test_c01x` / `test_c01w` / `test_i01l` 全绿。
- 活验：3080 静态逐请求读盘，刷新即见。

**不算 G0**。未 commit。
