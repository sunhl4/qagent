# L1-03 · 加包说明对齐 Cirq 已接线

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | S2 / L1-03-how |
| 范围 | `qagent/contracts/engines/HOW_TO_ADD.md` · `docs/execution/L1-03_how.md` · `qagent/tests/test_l103_how.py` |
| 层 | Layer 1 造包。不是客户 Agent，不是第三套 loop |
| 状态 | 文案对齐。Cirq 已是 wired 范例。再加包仍先 reserved。不算接线 Pennylane。不算 G3。 |

## 产品锁

- Cirq **已经**在 `engines[]` 且 wired，是互通范例。`provenance` 不是 `qccd-twin`，不许发 `twin_id`。
- 再加一个包（Pennylane / 真机）仍按 `HOW_TO_ADD.md`：**先 reserved**，不要一上来写进 `engines[]`。
- 保留：不要新写 agent；未接线禁止 `import` 核；句柄只有 `circuit_id` / `asset_id` / `twin_id`；只有 ionstack TwinRun 能发 `twin_id`。

## 不做什么

不改 `catalog.json`、ports、policy、`qagent/src` adapters、`run_tests.py`、`PROGRESS.md`。不 commit。不算接线 Pennylane。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_l103_wire.py
PYTHONPATH=src python3 tests/test_l103_how.py
```
