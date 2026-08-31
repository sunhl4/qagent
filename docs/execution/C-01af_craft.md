# C-01af · 商业工艺：焦点、打印、空状态

| 状态 | 完成 · 只动 `app.css`。命令条焦点收成单一边框；新增 `@media print`（白纸、藏轨/命令条/顶栏按钮）；空状态仍两条入口并锁进测。**不算 G0**。**未 commit** |
| --- | --- |

## 为什么

执行计划第四刀（C-01ae 对话列表之前）。M1/M2 已达成，这波是 Linear/Stripe 那层工艺：键盘可达、回答可打印带走、空状态不堆 chips。

## 改了什么（全部在 `apps/customer-shell/app.css`）

- 焦点一套：`.composer:focus-within` 去掉 `0 0 0 1px` 第二圈，只留边框变色；`a:focus-visible` 并入按钮的 ion 描边规则。
- `@media print`：body 白纸墨字；`.app` 退 grid 为块；藏 `.top-actions` / `.inbox` / `.composer`；助手回答变「上粗线文章块」，表格/代码/电路图/许可单换浅色可读版；页脚留公司名。电路 SVG 三色（`#2a3846` 线 / `#8ea0b0` 标 / `#6ba3c7` 门）在白纸上均可读，JS 不动。
- 空状态：不改行为，把「两条入口、packs 隐藏」锁进测。

## 没动什么

- `app.js` 一行不动。许可单、批准路径、轮询容错全留。
- 布局锁、禁词、三句柄全留。无 `ionstack_twin_run`、无 `twin_id=`、无 `a2_chem_pes`。
- reduced-motion 停脉冲在 C-01ad 已锁，本波不重复。

## 验证

- `tests/test_c01af.py` 六项全绿，已挂 `run_tests.py`。
- 回归：`test_c01aa` / `test_c01z` / `test_c01y` / `test_c01ab` / `test_c01ac` / `test_c01ad` / `test_c01x` / `test_c01w` / `test_i01l` 全绿。
- 活验：3080 静态逐请求读盘，刷新即见；打印预览可见白纸回答。

**不算 G0**。未 commit。
