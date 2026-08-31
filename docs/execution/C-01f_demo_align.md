# C-01f · G0 / G2 剧本文案对齐已落地的脸

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P |
| 范围 | `docs/execution/G0_demo.md` · `docs/execution/G2_demo.md` · `qagent/tests/test_c01f.py` |
| 状态 | 文案对齐 C-01e 脸。文本测绿。不算过门。 |

## 产品锁

- **G0**：打开 3080 后，若工作设置未就绪，设置对话框会自动打开。模型仍要**人填模型**。扫氢分子 / H₂、3080、3081、禁止假 `twin_id` 保持。
- **G2**：已签收的回执可以在 3080 下载短 JSON，并在脸上点核验。换机器仍跑 `python3 scripts/verify_receipt.py receipt.json`。租户 / TENANT、回执、IBM、绿封条保持。
- 句柄只有 `circuit_id` / `asset_id` / `twin_id`。不发明第四个。
- 人还没走完之前，门禁未过。不铸 `twin_id`。不改 `G1_demo.md`。

## 不做什么

不改 `qagent/src/**`、customer-shell、`run_tests.py`、`PROGRESS.md`、`G1_demo.md`、`G3_eval.md`。不加第三套 agent loop。不 commit。本包只对齐剧本文案，不是 G0 / G2 过门声明。
