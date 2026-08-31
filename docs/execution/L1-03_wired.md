# L1-03 · Cirq reserved→wired

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | S2 / L1-03-wire |
| 范围 | 把 `reserved_engines.cirq` 拷进 `engines[]` 并接线。五包顺序不变 |
| 层 | Layer 1 造包。不是客户 Agent，不是第三套 loop |
| 状态 | **Cirq 已接线**。engines 已含 cirq |

## 当前冻结（接线后）

`list_engines()` 仍只读 `catalog.engines[]`。五包 `qdata` / `qchem` / `ionstack` / `route` / `qiskit` 打头且 wired。Cirq 在五包后面，`status=wired`，`kind=interop`。

`reserved_engines` 不再有 cirq 行。不要两边各一份还说 reserved。

模拟器 provenance 是 `cirq`，不是 `qccd-twin`。Cirq 不是机器，不许发 `twin_id`。句柄仍只有 `circuit_id` / `asset_id` / `twin_id`。

`qagent/src` 与 `packages/qagent-cirq` 禁止 `import cirq`。`packages/qagent-cirq` 的 execute 仍只 `invoke()` / `registerInvokeTool`。

E22：`cirq_simulator_run` allow，载荷无第三句柄，`provenance=cirq`。不要加 E23。不要加 Q-c06。

## 改了什么

| 处 | 改动 |
|----|------|
| `catalog.json` | cirq 从 `reserved_engines` 拷进 `engines[]`，`status=wired`。`reserved_engines` 留空数组 |
| `ports.json` | cirq port `status=wired`。`forbidden_imports` 仍含 `cirq` |
| `policy.json` | 从 `forbidden_tool_names` 拿掉三个 `cirq_*`。`R-CIRQ-NO-TWIN` 挡 `claim_twin_id`。lab 可见，学 aer |
| `adapters/cirq.py` | `WiredCirq`。`simulator_run` 回 `provenance=cirq`。电路只经 pin。不发 `twin_id` |
| `PortRegistry` / `invoke` | 挂 `cirq: WiredCirq`。`cirq_simulator_run` + `claim_twin_id` 记 ELN `claim_blocked` |

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_l103.py
PYTHONPATH=src python3 tests/test_l103_wire.py
```

## 不做

- 不改 `run_tests.py`、`PROGRESS.md`、agent.py。
- 不铸 `twin_id`。不 commit。不 `import cirq`。
- 不加 E23。不加 Q-c06。
