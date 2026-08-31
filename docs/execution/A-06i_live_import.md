# A-06i · 活 import

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | A-06i |
| 范围 | 只本笔记 + `qagent/tests/test_a06i.py` |
| 未改 | `qagent/src/**` · `wrappers/interop.py` · `test_a06g.py` · `run_tests.py` · `PROGRESS.md` · ionstack 核 · workplace 密钥 · `chat.py` |
| 状态 | `QAGENT_IONSTACK_HOME=/Users/shl/Q-software` 下 `invoke("qiskit_import_circuit", "lab", {})` 得 `circuit_id=circ_48613db9e404`、`n_qubits=2`。同一次 `call_interop("import")` 的 `n_qubits=2`，`backend=ionstack.interop`。fallback 是 `int((live or {}).get("n_qubits") or 2)`，本轮 interop 成功，不是 fallback。无 `twin_id`。provenance 不是 `qccd-twin`。**不算 G0**。未 commit。 |

## 产品锁

- 完成线是 `invoke("qiskit_import_circuit", "lab", {})` 拿到 `circuit_id` 与 `n_qubits`，且 `n_qubits` 等于同一 qasm 下 `call_interop("import")` 的 `n_qubits`。
- `call_interop("import")` 走 `wrappers/interop.py`。成功则 `WiredQiskit.import_circuit` 用 live `n_qubits`。interop 失败才 fallback `or 2`。interop 失败当绿 = 没做完。
- 测里 `export QAGENT_IONSTACK_HOME=/Users/shl/Q-software`。不 `apply_env()`。不读本机 `workplace.json`。可隔离 `QAGENT_DATA_DIR`。
- 不铸 `twin_id`。只有 TwinRun 能发 `twin_id`。句柄只有 `circuit_id` / `asset_id` / `twin_id`。
- CAL / shuttle 不进工具。
- **不算 G0**。skip 当绿 = 没做完。interop 失败必须失败，不要 skip。

## 2026-08-27 真实对照

HOME：`QAGENT_IONSTACK_HOME=/Users/shl/Q-software`（仓根 `.venv/bin/python` 能 `import ionstack` 与 `qiskit`；本机该 HOME 的 `.venv` 有 `qiskit_qasm3_import`，才能吃默认 `OPENQASM 3.0`）。store 隔离在 `qagent/.qagent/test-a06i-store`。不 `apply_env()`。不读 `workplace.json`。

同一 qasm（`invoke(..., {})` 走 `_DEFAULT_QASM`）：

```text
OPENQASM 3.0;
include "stdgates.inc";
qubit[2] q;
h q[0];
cx q[0], q[1];
```

调用：

```text
invoke("qiskit_import_circuit", "lab", {})
call_interop("import", {"qasm3": _DEFAULT_QASM})
```

`import`：`status=ok`。`n_qubits=2`。无 `twin_id`。

fallback（interop 失败时 `int((live or {}).get("n_qubits") or 2)`）：

```json
2
```

本轮 `invoke("qiskit_import_circuit")` 活 payload：

```json
{"circuit_id": "circ_48613db9e404", "n_qubits": 2}
```

同一次 `call_interop("import")` 活包（invoke 的 `n_qubits` 取自这份）：

```json
{"n_qubits": 2, "n_instructions": 2, "backend": "ionstack.interop"}
```

| 字段 | 值 |
|------|-----|
| circuit_id | `circ_48613db9e404` |
| invoke status | `ok` |
| n_qubits | `2` |
| interop n_qubits | `2` |
| n_instructions | `2` |
| fallback n_qubits | `2` |
| 是否 fallback | 否（`call_interop("import")` 成功，`backend=ionstack.interop`；invoke 的 `n_qubits` 等于这份 live） |
| payload `twin_id` | 无 |
| provenance `qccd-twin` | 无 |

`status=ok` 是 invoke 结果，不是 payload 字段。payload 无 `ok`。无 `twin_id`。provenance 不是 `qccd-twin`。

独立再打一次同一 qasm 的 `call_interop("import")` 必须成功（有 `n_qubits`，`backend=ionstack.interop`）。invoke 的 `n_qubits` 必须等于这次 interop 的 `n_qubits`。默认电路也是 2 比特，所以单看数字等于 fallback 不够；完成线是 interop 成功且数字来自 live 包。

## 不算什么

- **不算 G0**。没在 3080 填模型，没走「扫氢分子」。
- **不算 G2**。没有客户面回执演示。
- **不算接线 Pennylane**。Pennylane 仍只 reserved。
- 不算改了合同里的本地 `n_qubits or 2` 卡。那条是 interop 失败时的 fallback，不是本包活 import。
- 未改 `adapters/qiskit.py` / `wrappers/interop.py`。未 commit。

## 测

```bash
cd /Users/shl/nvidia/qagent
QAGENT_IONSTACK_HOME=/Users/shl/Q-software PYTHONPATH=src python3 tests/test_a06i.py
PYTHONPATH=src python3 tests/run_tests.py
```

invoke 的 `n_qubits` 必须等于这次 invoke 打到的 `call_interop("import")` 活包。interop 失败必须失败。fallback 当绿 = 没做完。skip 当绿 = 没做完。不 commit。
