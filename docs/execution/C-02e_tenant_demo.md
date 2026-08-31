# C-02e · G2 双客户剧本对齐 3080 `?tenant=`

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P |
| 范围 | `docs/execution/G2_demo.md` · `qagent/tests/test_c02e.py` |
| 状态 | 文案对齐 3080 `?tenant=`。文本测绿。不算过门。 |

## 产品锁

- **G2 两位客户**：3080 可以用 `?tenant=`（例如 cust-a / cust-b）带上租户；请求头仍是租户头。空租户是组内，看见全部。
- 已签收的回执可以在 3080 下载短 JSON，并在脸上点核验。换机器仍跑 `python3 scripts/verify_receipt.py receipt.json`。租户 / TENANT、回执、IBM、绿封条保持。
- 句柄只有 `circuit_id` / `asset_id` / `twin_id`。不发明第四个。
- 人还没走完之前，门禁未过。不铸 `twin_id`。不改 `G0_demo.md` / `G1_demo.md`。

## 不做什么

不改 `qagent/src/**`、customer-shell、`run_tests.py`、`PROGRESS.md`、`G0_demo.md`、`G1_demo.md`。不加第三套 agent loop。不 commit。本包只对齐剧本文案，不是 G2 过门声明。
