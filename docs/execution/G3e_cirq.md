# G3e · G3 评测清单对齐 Cirq 已接线

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | Q · G3e |
| 范围 | `docs/execution/G3_eval.md` · `qagent/tests/test_g3e.py` |
| 状态 | 文案对齐 L1-03 接线。文本测绿。不算 G3。 |

## 产品锁

- 硬轨来源：Aer / IBM / 本地卡 / Cirq 不许写成 `qccd-twin`。Cirq 已接线，`provenance=cirq`，不是我们的机器，不许发 `twin_id`。
- Codex 仍 stub。不 spawn 官方 Codex，不调官方 Codex。
- 保留 `test_g3_script`：30、Q-h06、stub、`PYTHONPATH=src python3 tests/run_qagent_vs_codex.py`、bare Codex、`may_fail`、30/30。Q-h06 已离线可跑。skip 当绿=没做完。**不算 G3 过门。**
- 句柄只有 `circuit_id` / `asset_id` / `twin_id`。不发明第四个。
- 本包只对齐评测清单文案。不算 G3。不是 G3 过门。

## 不做什么

不改 `qagent/src/**`、customer-shell、`run_tests.py`、`PROGRESS.md`、`G0_demo.md`、`G1_demo.md`、`G2_demo.md`、`run_qagent_vs_codex.py`、`qagent-eval.yml`。不加 Q-c06。不加第三套 agent loop。不 commit。

## 测

```text
cd /Users/shl/nvidia/qagent && PYTHONPATH=src python3 tests/test_g3_script.py
PYTHONPATH=src python3 tests/test_g3e.py
```
