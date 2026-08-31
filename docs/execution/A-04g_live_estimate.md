# A-04g · 活 interop 估计

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | S2 · A-04g |
| 范围 | 只本笔记 + `qagent/tests/test_a04g.py` |
| 未改 | `qagent/src/**` · `wrappers/interop.py` · `test_a04.py` · `run_tests.py` · `PROGRESS.md` · ionstack 核 · workplace 密钥 · `chat.py` |
| 状态 | `QAGENT_IONSTACK_HOME=/Users/shl/Q-software` 下 `invoke("ionstack_compile_estimate")` 打到活 `makespan_ns=3040.0`。同一 `DEFAULT_CIRCUIT` 的 `mapqccd_estimate` 公式是 `4800.0`（`1200 * n_qubits * n_instructions`）。活值 ≠ 公式，不是 fallback。payload **无** `ok` / `twin_id`。**不算 G0**。未 commit。 |

## 产品锁

- 完成线是 `invoke("ionstack_compile_estimate", "lab", {"circuit": DEFAULT_CIRCUIT})` 的活 interop 估计，不是 `1200 * n_qubits * n_instructions` 公式。
- `call_interop("estimate")` 走 `wrappers/interop.py`。成功则 `WiredIonstack.compile_estimate` 用 live payload（须有 `makespan_ns` 且无 `ok`）。interop 失败才 fallback `mapqccd_estimate`。公式 fallback 当绿 = 没做完。
- 测里 `export QAGENT_IONSTACK_HOME=/Users/shl/Q-software`。不 `apply_env()`。不读本机 `workplace.json`。不设 `QAGENT_ROUTE_BACKEND=route-alt`。可隔离 `QAGENT_DATA_DIR`。
- `compile_estimate` 不许有 `ok` / `twin_id` / `signoff`。只有 TwinRun 能发 `twin_id`。句柄只有 `circuit_id` / `asset_id` / `twin_id`。
- CAL / shuttle 不进工具。
- **不算 G0**。skip 当绿 = 没做完。interop 失败必须失败，不要 skip。

## 2026-08-27 真实对照

HOME：`QAGENT_IONSTACK_HOME=/Users/shl/Q-software`（仓根 `.venv/bin/python` 能 `import ionstack`）。`QAGENT_ROUTE_BACKEND` 未设。store 隔离在 `qagent/.qagent/test-a04g-store`。不 `apply_env()`。不读 `workplace.json`。

调用：

```text
invoke("ionstack_compile_estimate", "lab", {"circuit": eval_run.DEFAULT_CIRCUIT})
```

`DEFAULT_CIRCUIT`：`n_qubits=2`，`n_instructions=2`。

公式（`mapqccd_estimate`，`1200 * n_qubits * n_instructions`）：

```json
{"makespan_ns": 4800.0, "summary": {"backend": "mapqccd", "n_qubits": 2, "n_instructions": 2}}
```

`call_interop("estimate")` 与 `invoke` 同一活 payload：

```json
{"makespan_ns": 3040.0, "summary": {"backend": "mapqccd", "n_qubits": 2}}
```

| 字段 | 值 |
|------|-----|
| invoke status | `ok` |
| live makespan_ns | `3040.0` |
| 公式 makespan_ns | `4800.0` |
| 公式 | `1200 * 2 * 2 = 4800` |
| 是否公式 fallback | 否（`3040.0 ≠ 4800.0`） |
| payload `ok` | 无 |
| payload `twin_id` | 无 |

`status=ok` 是 invoke 结果，不是 payload 字段。payload 无 `ok`。无 `twin_id`。无 `signoff`。

## 不算什么

- **不算 G0**。没在 3080 填模型，没走「扫氢分子」。
- **不算 G2**。没有客户面回执演示。
- **不算接线 Pennylane**。Pennylane 仍只 reserved。
- 不算 `QAGENT_ROUTE_BACKEND=route-alt` 的另一套公式（`1500 * n + 100`）。本包不设 `route-alt`。
- 不算改了 [A-04_route.md](A-04_route.md) 的合同估计。那条是公式 / 换后端，不是活 interop。
- 未改 `adapters/ionstack.py` / `wrappers/interop.py`。未 commit。

## 测

```bash
cd /Users/shl/nvidia/qagent
QAGENT_IONSTACK_HOME=/Users/shl/Q-software PYTHONPATH=src python3 tests/test_a04g.py
PYTHONPATH=src python3 tests/run_tests.py
```

活 `makespan_ns` 必须与公式不同。interop 失败必须失败。skip 当绿 = 没做完。不 commit。
