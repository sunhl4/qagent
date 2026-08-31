# G1e · G1 剧本对齐 Cirq 已接线

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P · G1e |
| 范围 | `docs/execution/G1_demo.md` · `qagent/tests/test_g1e.py` |
| 状态 | 文案对齐 L1-03 接线。文本测绿。不算 G1 过门。 |

## 产品锁

- 「哪些包」和「当场要看见」：五包 `qdata` / `qchem` / `ionstack` / `route` / `qiskit` 仍打头且 wired。Cirq 已在 `engines[]`，`kind=interop`，`provenance=cirq`，不是 `qccd-twin`，不许发 `twin_id`。
- 不要把 Cirq 说成我们的机器，不要铸 `twin_id`。
- 保留：3080、3081、`list_engines`、`makespan_ns`、不会伪造或假 `twin_id`、Aer、`provenance`。
- 句柄只有 `circuit_id` / `asset_id` / `twin_id`。不发明第四个。
- 人还没走完之前，门禁未过。不宣称通过，不对外说门禁演完了。

## 不做什么

不改 `qagent/src/**`、customer-shell、`run_tests.py`、`PROGRESS.md`、`G0_demo.md`、`G2_demo.md`。不加第三套 agent loop。不 commit。本包只对齐剧本文案，不是 G1 过门声明。

## 测

```text
cd /Users/shl/nvidia/qagent && PYTHONPATH=src python3 tests/test_g1_script.py
PYTHONPATH=src python3 tests/test_g1e.py
```
