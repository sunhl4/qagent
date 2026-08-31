# A-02i · qchem 后 dequant

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | A-02i |
| 范围 | 只本笔记 + `qagent/tests/test_a02i.py` |
| 未改 | `qagent/src/**` · `test_a02h.py` · `test_a01k.py` · `run_tests.py` · `PROGRESS.md` · qchem / qdata 核 · workplace 密钥 · `chat.py` · `invoke.py` · `agent.py` |
| 状态 | 同一 `QAGENT_DATA_DIR`：先 `invoke("qchem_run")` 打到 `source=qchem-cli` + `asset_id`，再 `invoke("qdata_dequant_gate")` 读同一本地 store。有 `b3.verdict`。无 `twin_id`。不要 `force_verdict`。**不算 G0**。skip 当绿 = 没做完 |

## 产品锁

- 完成线是同一隔离 store 上先 `qchem_run`（`qchem-cli`）再 `qdata_dequant_gate` 见到同一 `asset_id` 与 `b3.verdict`。活卡由 [A-02h](A-02h_persist.md) 写入现有 `qdata.json`，本包不改适配器。
- `dequant_gate` 读同一 `QAGENT_DATA_DIR` 的本地 store。不铸 `twin_id`。无 Pauli 全文。句柄只有 `circuit_id` / `asset_id` / `twin_id`，qchem 只许出 `asset_id`。
- 测里 `export QAGENT_QCHEM_HOME=/Users/shl/nvidia/qcchem-qml-md`。隔离 `QAGENT_DATA_DIR`（run 与 dequant 同一目录）。不 `apply_env()`。不读本机 `workplace.json`。不设 `QAGENT_QDATA_URL`。
- lab 调 `qdata_dequant_gate` 带 `force_verdict=quantum_wins` 是 deny。不要 `force_verdict`。
- **不算 G0**。skip 当绿 = 没做完。没有 `b3.verdict` 或 `asset_id` 对不上必须失败。

## 2026-08-27 真实 dequant payload

HOME：`QAGENT_QCHEM_HOME=/Users/shl/nvidia/qcchem-qml-md`（`.venv/bin/qchem-run` 能跑 `minimal_vqe`）。store 隔离在 `qagent/.qagent/test-a02i-store`。`QAGENT_QDATA_URL` 未设。不 `apply_env()`。不读 `workplace.json`。

调用（同一 `QAGENT_DATA_DIR`）：

```text
invoke("qchem_run", "lab", {"scenario": "minimal_vqe"})
invoke("qdata_dequant_gate", "lab", {"asset_id": "<run 的 asset_id>"})
```

不要 force_verdict。

run：`status=ok`。`payload.summary.source=qchem-cli`。有 `asset_id`。无 `twin_id`。

dequant：`status=ok`。同一 `asset_id`。有 `b3.verdict`。无 `twin_id`。无 Pauli 全文。

抄到的句柄：

| 字段 | 值 |
|------|-----|
| asset_id | `asset_8b00a737b406` |
| source（run） | `qchem-cli` |
| recipe | `minimal_vqe` |
| b3.verdict | `inconclusive` |

dequant payload 原文：

```json
{"b3": {"verdict": "inconclusive", "qem_contract_ok": false}, "qem_contract_ok": false}
```

run payload 原文：

```json
{
  "asset_id": "asset_8b00a737b406",
  "summary": {
    "energy_after_variational": -1.1372759415451792,
    "energy_pauli_protocol": -1.1372759415451792,
    "experiment_id": null,
    "scf_energy": -1.116714325062552,
    "source": "qchem-cli"
  }
}
```

## 不算什么

- **不算 G0**。没在 3080 填模型，没走「扫氢分子」。
- 不算接线 Pennylane。Pennylane 仍 reserved。
- 不算改了 [A-02h](A-02h_persist.md) 的落卡，也不算改了 [A-01k](A-01k_dequant.md) 的 qdata-cli dequant。
- 不算 HTTP `:8787` 已通。本包打的是活 `qchem-run` 经 `invoke` 落同一本地 store，再读 dequant gate。

## 测

```bash
cd /Users/shl/nvidia/qagent
export QAGENT_QCHEM_HOME=/Users/shl/nvidia/qcchem-qml-md
PYTHONPATH=src python3 tests/test_a02i.py
PYTHONPATH=src python3 tests/run_tests.py
```

没有 `b3.verdict` 或 `asset_id` 对不上必须失败。skip 当绿 = 没做完。不 commit。未 commit。
