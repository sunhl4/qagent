# L1-03 · Cirq 引擎包（reserved，不进五包目录）

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-26 |
| 角色 | S2 |
| 范围 | Cirq pack：合同 + `fill()` + deny stub + `packages/qagent-cirq` |
| 层 | Layer 1 造包。不是客户 Agent，不是第三套 loop |

## 结论

`catalog.json` 的 `engines[]` **仍是五包**（qdata / qchem / ionstack / route / qiskit）。Cirq 已在 `future_examples`，但还没进 `engines[]`。把它写进 `engines[]` 会立刻打红：

- `qagent/tests/run_tests.py` `test_engines()`：`ids ==` 五包
- `qagent/tests/test_engines.py`：同样五包
- `qagent/tests/test_a05.py` `test_engines_reserved_stay_reserved`：`assert "cirq" not in ids`
- `test_company_shell`：`payload["engines"]` 也是这五 id
- `test_engines()` 还要求 `all(e.status == "wired")`

本流 **不许改 `run_tests.py`**，也不能改 `test_a05.py` / `registry.py`。所以 Cirq **保持 reserved**：写在 `reserved_engines`，不进 `list_engines()`。调度以后把那一行拷进 `engines[]`，并放松上述断言，才允许 reserved → minimal wired。

未接线不 import 核。`qagent/src` 与 `packages/qagent-cirq` 没有 `import cirq` / `qiskit` / `qdata` / `ionstack` / `qchem`。`ports.json` `forbidden_imports` 已加 `cirq`。

输出不含第三句柄。电路只经 `circuit_id` / pin。模拟器 provenance 合同是 `cirq`，不是 `qccd-twin`。`PortRegistry` 未挂 `cirq`；invoke 在 deny 处闭合，不会走到未知 port。

## 行为

| 条件 | 结果 |
|------|------|
| `list_engines()` / `qagent_list_engines` | 仍五包 wired。Cirq 不在 ids |
| `catalog.reserved_engines` | `id=cirq`，`status=reserved`，`kind=interop`，句柄 `circuit_id` + `provenance` |
| `cirq_*` decide / invoke | deny（`forbidden_tool_names` + `R-CIRQ-RESERVED` + hidden） |
| `ReservedCirq.*` | `fill()` → `FillSlotError`（S-CIRQ-01/02/03） |
| `packages/qagent-cirq` execute | `registerInvokeTool` → `invoke()`。未挂进 dsh profile |
| E22 | 句柄合同：`cirq_simulator_run` deny，载荷无第三句柄。`status=empty`，不进 E01–E21 implemented 集合 |

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_l103.py
PYTHONPATH=src python3 tests/run_tests.py
```

`test_l103.py` 退出 0。`run_tests.py` 未改；五包断言仍绿，因为 Cirq 不在 `engines[]`。

**E22 注：** `load_eval_cases()` 会 glob 到 `E22.json`。`run_tests.py` / `test_contracts.py` 仍写死 `E01`–`E21`。调度改 `range(1, 22)` 之前，跑全量 `test_contracts` 会因多出 E22 而红。`test_l103` 单独跑 `run_evals("E22")`。E01–E21 id 未改。

## 不做

- 不把 Cirq 写进 `engines[]`（会打红五包测试）。
- 不改 `run_tests.py`、`PROGRESS.md`、chat / ionstack / qdata / customer-shell / `product_eval.py`。
- 不 `import cirq`。不铸第三句柄。不新写 agent loop。
- 不 commit。

## 剩（调度）

1. 把 `reserved_engines.cirq` 推进 `engines[]`，`test_engines` / `test_a05` / `company_shell` 放宽到六包。
2. `PortRegistry` 挂 `cirq`（`ReservedCirq` 或以后的 wired adapter）。
3. `load_eval_cases` 的 E01–E21 冻结改为含 E22。
4. 然后才允许 reserved → minimal wired：`execute` 仍走 `invoke()`，provenance=`cirq`，电路只 pin。
