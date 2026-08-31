# A-06g · 活 Aer

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | A-06g |
| 范围 | 只本笔记 + `qagent/tests/test_a06g.py` |
| 未改 | `qagent/src/**` · `wrappers/interop.py` · `run_tests.py` · `PROGRESS.md` · ionstack 核 · workplace 密钥 · `chat.py` |
| 状态 | `QAGENT_IONSTACK_HOME=/Users/shl/Q-software` 下 `invoke("qiskit_import_circuit")` 得 `circuit_id=circ_48613db9e404`，再 `invoke("qiskit_aer_run")` 打到活 `provenance=aer`、`counts={"11": 3, "00": 5}`、`shots_actual=8`。同一次 `call_interop("aer")` 的 counts 一致。公式 `_counts(8)` 是 `{"00": 4, "11": 4}`，本轮不是公式。无 `twin_id`。provenance 不是 `qccd-twin`。**不算 G0**。未 commit。 |

## 产品锁

- 完成线是 `invoke("qiskit_import_circuit", "lab", {})` 拿到 `circuit_id`，再 `invoke("qiskit_aer_run", "lab", {"circuit_id": ..., "shots": 8})` 的活 Aer，不是 `adapters/qiskit.py` 里的 `_counts(shots)`。
- `call_interop("aer")` 走 `wrappers/interop.py`。成功则 `WiredQiskit.aer_run` 用 live `counts`。interop 失败才 fallback `_counts`。公式 fallback 当绿 = 没做完。
- 测里 `export QAGENT_IONSTACK_HOME=/Users/shl/Q-software`。不 `apply_env()`。不读本机 `workplace.json`。可隔离 `QAGENT_DATA_DIR`。
- Aer 的 `provenance` 必须是 `aer`，不许 `qccd-twin`。不铸 `twin_id`。只有 TwinRun 能发 `twin_id`。句柄只有 `circuit_id` / `asset_id` / `twin_id`。
- CAL / shuttle 不进工具。
- **不算 G0**。skip 当绿 = 没做完。interop 失败必须失败，不要 skip。

## 2026-08-27 真实对照

HOME：`QAGENT_IONSTACK_HOME=/Users/shl/Q-software`（仓根 `.venv/bin/python` 能 `import ionstack` 与 `qiskit_aer`）。store 隔离在 `qagent/.qagent/test-a06g-store`。不 `apply_env()`。不读 `workplace.json`。

调用：

```text
invoke("qiskit_import_circuit", "lab", {})
invoke("qiskit_aer_run", "lab", {"circuit_id": "circ_48613db9e404", "shots": 8})
call_interop("aer", {"circuit_id": "circ_48613db9e404", "shots": 8})
```

`import`：`status=ok`。`n_qubits=2`。无 `twin_id`。

公式（`_counts(8)`，`{"00": shots//2, "11": shots - shots//2}`）：

```json
{"00": 4, "11": 4}
```

本轮 `invoke("qiskit_aer_run")` 活 payload：

```json
{"provenance": "aer", "counts": {"11": 3, "00": 5}, "shots_actual": 8}
```

同一次 `call_interop("aer")` 活包（invoke 用的就是这份 counts）：

```json
{"provenance": "aer", "counts": {"11": 3, "00": 5}, "shots_actual": 8, "backend": "ionstack.interop"}
```

| 字段 | 值 |
|------|-----|
| circuit_id | `circ_48613db9e404` |
| invoke status | `ok` |
| provenance | `aer` |
| counts | `{"11": 3, "00": 5}` |
| shots_actual | `8` |
| 公式 counts | `{"00": 4, "11": 4}` |
| 是否公式 fallback | 否（`{"11": 3, "00": 5} ≠ {"00": 4, "11": 4}`，且 `backend=ionstack.interop`） |
| payload `twin_id` | 无 |
| provenance `qccd-twin` | 无 |

`status=ok` 是 invoke 结果，不是 payload 字段。payload 无 `ok`。无 `twin_id`。provenance 是 `aer`，不是 `qccd-twin`。

独立再打一次 `call_interop("aer")` 必须成功（`provenance=aer`，有 counts）。Aer 抽样，另一次独立 run 的 counts 可以不同；完成线是 invoke 的 counts 等于这次 invoke 打到的 interop 活包，不是 `_counts`。

## 不算什么

- **不算 G0**。没在 3080 填模型，没走「扫氢分子」。
- **不算 G2**。没有客户面回执演示。
- **不算接线 Pennylane**。Pennylane 仍只 reserved。
- 不算改了合同里的本地 `_counts` 卡。那条是 interop 失败时的 fallback，不是本包活 Aer。
- 未改 `adapters/qiskit.py` / `wrappers/interop.py`。未 commit。

## 测

```bash
cd /Users/shl/nvidia/qagent
QAGENT_IONSTACK_HOME=/Users/shl/Q-software PYTHONPATH=src python3 tests/test_a06g.py
PYTHONPATH=src python3 tests/run_tests.py
```

invoke 的 counts 必须等于这次 invoke 打到的 `call_interop("aer")` 活包。interop 失败必须失败。公式 fallback 当绿 = 没做完。skip 当绿 = 没做完。不 commit。
