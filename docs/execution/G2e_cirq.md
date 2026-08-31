# G2e · G2 客户剧本对齐 Cirq 已接线

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P · G2e |
| 范围 | `docs/execution/G2_demo.md` · `qagent/tests/test_g2e.py` |
| 状态 | 文案对齐 L1-03 接线。文本测绿。不算 G2 过门。 |

## 产品锁

- G2 客户清单：「Aer / IBM / 本地卡 / Cirq 都不许冒充」。Cirq 不是我们的机器，不许铸 `twin_id`，provenance 不许写成 `qccd-twin`。
- 保留 C-01c / C-01f：租户、回执、IBM、绿封条、`已签收的回执可以在 3080 下载短 JSON`、`脸上点核验`、`python3 scripts/verify_receipt.py receipt.json`、`人还没走完之前，门禁未过`。
- 句柄只有 `circuit_id` / `asset_id` / `twin_id`。租户只写租户 / TENANT，不发明第四个。
- 人还没走完之前，门禁未过。不宣称通过。不算 G2。

## 不做什么

不改 `qagent/src/**`、customer-shell、`run_tests.py`、`PROGRESS.md`、`G0_demo.md`、`G1_demo.md`、`G3_eval.md`。不加第三套 agent loop。不 commit。本包只对齐剧本文案，不是 G2 过门声明。

## 测

```text
cd /Users/shl/nvidia/qagent && PYTHONPATH=src python3 tests/test_c01c.py
PYTHONPATH=src python3 tests/test_c01f.py
PYTHONPATH=src python3 tests/test_c02e.py
PYTHONPATH=src python3 tests/test_g2e.py
```
