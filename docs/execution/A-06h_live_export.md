# A-06h · 活 export

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | A-06h |
| 范围 | 只本笔记 + `qagent/tests/test_a06h.py` |
| 未改 | `qagent/src/**` · `wrappers/interop.py` · `test_a06g.py` · `run_tests.py` · `PROGRESS.md` · ionstack 核 · workplace 密钥 · `chat.py` |
| 状态 | `QAGENT_IONSTACK_HOME=/Users/shl/Q-software` 下 `invoke("qiskit_import_circuit")` 得 `circuit_id=circ_48613db9e404`，再 `invoke("qiskit_export_circuit")` 打到活 `qasm3` 前几行是 `q_0: ┤ H ├──■──`。同一次 `call_interop("export")` 的 `qasm3` 一致，`backend=ionstack.interop`。本地 `_DEFAULT_QASM` 是 `OPENQASM 3.0;` 开头，本轮不是默认。无 `twin_id`。**不算 G0**。未 commit。 |

## 产品锁

- 完成线是 `invoke("qiskit_import_circuit", "lab", {})` 拿到 `circuit_id`，再 `invoke("qiskit_export_circuit", "lab", {"circuit_id": ...})` 的活 export，不是 `adapters/qiskit.py` 里的 `_DEFAULT_QASM`。
- `call_interop("export")` 走 `wrappers/interop.py`。成功则 `WiredQiskit.export_circuit` 用 live `qasm3`。interop 失败才 fallback `_DEFAULT_QASM`。默认 fallback 当绿 = 没做完。若默认碰巧相同，必须另证 interop 成功且 `backend=ionstack.interop`。
- 测里 `export QAGENT_IONSTACK_HOME=/Users/shl/Q-software`。不 `apply_env()`。不读本机 `workplace.json`。可隔离 `QAGENT_DATA_DIR`。
- 不铸 `twin_id`。只有 TwinRun 能发 `twin_id`。Aer / Qiskit provenance 不许 `qccd-twin`。句柄只有 `circuit_id` / `asset_id` / `twin_id`。
- CAL / shuttle 不进工具。
- **不算 G0**。skip 当绿 = 没做完。interop 失败必须失败，不要 skip。

## 2026-08-27 真实对照

HOME：`QAGENT_IONSTACK_HOME=/Users/shl/Q-software`（仓根 `.venv/bin/python` 能 `import ionstack` 与 `qiskit`）。store 隔离在 `qagent/.qagent/test-a06h-store`。不 `apply_env()`。不读 `workplace.json`。

调用：

```text
invoke("qiskit_import_circuit", "lab", {})
invoke("qiskit_export_circuit", "lab", {"circuit_id": "circ_48613db9e404"})
call_interop("export", {"body": {"n_qubits": 2}})
```

`import`：`status=ok`。`n_qubits=2`。无 `twin_id`。

默认（`_DEFAULT_QASM`）：

```text
OPENQASM 3.0;
include "stdgates.inc";
qubit[2] q;
h q[0];
cx q[0], q[1];
```

本轮 `invoke("qiskit_export_circuit")` 活 `qasm3` 前几行：

```text
     ┌───┐     
q_0: ┤ H ├──■──
     └───┘┌─┴─┐
q_1: ─────┤ X ├
          └───┘
```

同一次 `call_interop("export")` 活包（invoke 用的就是这份 `qasm3`）：

```json
{"qasm3": "     ┌───┐     \nq_0: ┤ H ├──■──\n     └───┘┌─┴─┐\nq_1: ─────┤ X ├\n          └───┘", "n_qubits": 2, "backend": "ionstack.interop"}
```

| 字段 | 值 |
|------|-----|
| circuit_id | `circ_48613db9e404` |
| invoke status | `ok` |
| body | `{"n_qubits": 2}` |
| qasm3 前几行 | `     ┌───┐     ` / `q_0: ┤ H ├──■──` / `     └───┘┌─┴─┐` |
| 默认 `_DEFAULT_QASM` 头 | `OPENQASM 3.0;` |
| 是否默认 fallback | 否（活 `qasm3` ≠ `_DEFAULT_QASM`，且 `backend=ionstack.interop`） |
| payload `twin_id` | 无 |
| provenance `qccd-twin` | 无 |

`status=ok` 是 invoke 结果，不是 payload 字段。payload 无 `ok`。无 `twin_id`。没有 `qccd-twin`。

独立再打一次 `call_interop("export", {"body": {"n_qubits": 2}})` 必须成功（有 `qasm3`，`backend=ionstack.interop`）。invoke 的 `qasm3` 必须等于这次 interop 的 `qasm3`。完成线不是本地 `_DEFAULT_QASM`。

## 不算什么

- **不算 G0**。没在 3080 填模型，没走「扫氢分子」。
- **不算 G2**。没有客户面回执演示。
- **不算接线 Pennylane**。Pennylane 仍只 reserved。
- 不算改了合同里的本地 `_DEFAULT_QASM` 卡。那条是 interop 失败时的 fallback，不是本包活 export。
- 未改 `adapters/qiskit.py` / `wrappers/interop.py`。未 commit。

## 测

```bash
cd /Users/shl/nvidia/qagent
QAGENT_IONSTACK_HOME=/Users/shl/Q-software PYTHONPATH=src python3 tests/test_a06h.py
PYTHONPATH=src python3 tests/run_tests.py
```

invoke 的 `qasm3` 必须等于这次 invoke 打到的 `call_interop("export")` 活包。interop 失败必须失败。默认 fallback 当绿 = 没做完。skip 当绿 = 没做完。不 commit。
