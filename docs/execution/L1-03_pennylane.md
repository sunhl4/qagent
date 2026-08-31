# L1-03-pl · Pennylane 引擎包（reserved，不接线）

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | S2 |
| 范围 | Pennylane pack：合同 + `fill()` + deny stub + `packages/qagent-pennylane` |
| 层 | Layer 1 造包。不是客户 Agent，不是第三套 loop |
| 状态 | **Pennylane 只在 `reserved_engines`**。未进 `engines[]`。不接线 |

## 结论

`catalog.json` 的 `engines[]` 仍是五包打头 + Cirq wired。Pennylane **只**写在 `reserved_engines`：

- `id=pennylane`，`status=reserved`，`kind=interop`
- 句柄只有 `circuit_id` + `provenance`（不要 `twin_id`）
- **禁止**把 pennylane 写进 `engines[]`
- Cirq 留在 `engines[]` wired，**不要**把 cirq 放回 `reserved_engines`

`list_engines()` / `qagent_list_engines` 的 ids 不含 `pennylane`。`test_a05` 的 `pennylane not in ids` 必须绿。

未接线不 import 核。`qagent/src` 与 `packages/qagent-pennylane` 没有 `import pennylane` / `cirq` / `qiskit` / `qdata` / `ionstack` / `qchem`。`ports.json` `forbidden_imports` 已加 `pennylane`。

输出不含第三句柄。电路只经 `circuit_id` / pin。模拟器 provenance 合同是 `pennylane`，不是 `qccd-twin`。`PortRegistry` 未挂 `pennylane`；invoke 在 deny 处闭合。

`future_examples` 不再把 cirq 当 future：`["pennylane","uqc-hardware"]`。

## 行为

| 条件 | 结果 |
|------|------|
| `list_engines()` / `qagent_list_engines` | 五包打头 + cirq wired。pennylane 不在 ids |
| `catalog.reserved_engines` | `id=pennylane`，`status=reserved`，`kind=interop`，句柄 `circuit_id` + `provenance` |
| `catalog.engines[]` | 无 pennylane 行。Cirq 仍 wired |
| `pennylane_*` decide / invoke | deny（`forbidden_tool_names` + `R-PENNYLANE-RESERVED` + hidden） |
| `claim_twin_id` | `R-PENNYLANE-NO-TWIN` deny |
| `ReservedPennylane.*` | `fill()` → `FillSlotError`（S-PL-01/02/03） |
| `packages/qagent-pennylane` execute | `registerInvokeTool` → `invoke()`。未挂进 dsh profile |
| CAL / shuttle / `qiskit_ibm_run` | 仍 forbid |
| E23 | **不加** |

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_l103_pl.py
PYTHONPATH=src python3 tests/test_l103.py
PYTHONPATH=src python3 tests/test_l103_wire.py
PYTHONPATH=src python3 tests/test_a05.py
```

`test_l103_pl.py` 退出 0。`run_tests.py` 未改。五包 + cirq 断言仍绿，因为 pennylane 不在 `engines[]`。

## 不做

- 不把 Pennylane 写进 `engines[]`（会打红 `test_a05` `pennylane not in ids`）。
- 不把 Cirq 放回 `reserved_engines`。不算 Cirq 未接线。
- 不改 `run_tests.py`、`PROGRESS.md`、chat / ionstack / qdata / customer-shell / `HOW_TO_ADD.md`。
- 不 `import pennylane`。不铸第三句柄。不新写 agent loop。
- 不挂 `PortRegistry`。不加 E23。不接线。
- 不 commit。

## 剩（调度）

1. 把 `reserved_engines.pennylane` 推进 `engines[]` 之前，先放宽 `test_a05` / `test_engines` 对 pennylane 的 listed 锁。
2. `PortRegistry` 挂 `pennylane`（`ReservedPennylane` 或以后的 wired adapter）。
3. 然后才允许 reserved → minimal wired：`execute` 仍走 `invoke()`，provenance=`pennylane`，电路只 pin。
