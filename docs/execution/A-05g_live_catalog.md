# A-05g · 活目录含卡

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | S1 · A-05g |
| 范围 | 只本笔记 + `qagent/tests/test_a05g.py` |
| 未改 | `qagent/src/**` · `test_a05.py` · `test_a05_live.py` · `test_a01g.py` · `A-05_live.md` · `run_tests.py` · `PROGRESS.md` · customer-shell · `chat.py` · qdata 核 · workplace 密钥 |
| 状态 | 同一 `QAGENT_DATA_DIR`：`invoke("qdata_run_recipe")` 打到 `source=qdata-cli` + `asset_id`，再 `invoke("qdata_list_assets")` 列表含该卡。≤20。无 Pauli / `twin_id`。**不算 G0**。**不算 G2**。**不算接线 Pennylane**。 |

## 产品锁

- 完成线是同一隔离 store 上先 `run_recipe` 再 `list_assets` 见到该 `asset_id`，不是 raw `qdata assets --store`。
- 测里 `export QAGENT_QDATA_HOME=/Users/shl/nvidia/qdata`。隔离 `QAGENT_DATA_DIR`（run 与 list 同一目录）。不 `apply_env()`。不读本机 `workplace.json`。不设 `QAGENT_QDATA_URL`（本包打 CLI 卡，不是 HTTP job）。
- 不铸 `twin_id`。无 Pauli 全文。无 bitstrings / OPENQASM。句柄只有 `circuit_id` / `asset_id` / `twin_id`，qdata 只许出 `asset_id`。目录最多 20 行。
- 旧 [A-05_live.md](A-05_live.md) 的「未打 / 未证明」合同不动。那条是 gated skip 探活，不是本包。
- **不算 G0 / G2**。**不算接线 Pennylane**。Pennylane 仍 reserved。
- skip 当绿 = 没做完。没有该 `asset_id` 必须失败。

## 2026-08-27 真实 list 行

HOME：`QAGENT_QDATA_HOME=/Users/shl/nvidia/qdata`（`.venv/bin/qdata` 有 `run`）。store 隔离在 `qagent/.qagent/test-a05g-store`。`QAGENT_QDATA_URL` 未设。

调用（同一 `QAGENT_DATA_DIR`）：

```text
invoke("qdata_run_recipe", "lab", {"name": "a2_spin_shadow", "shots": 8})
invoke("qdata_list_assets", "lab", {})
```

run：`status=ok`。`payload.summary.source=qdata-cli`。有 `asset_id`。无 `twin_id`。

list：`status=ok`。`assets` 长度 7（≤20）。其中有一行带刚才的 `asset_id`。行键只有 `kind` / `name` / `asset_id` / `recipe`。无 Pauli / bitstrings / OPENQASM。无 `twin_id`。

抄到的目录行：

```json
{"kind": "card", "name": "a2_spin_shadow", "asset_id": "asset_ffe79d915e4c", "recipe": "a2_spin_shadow"}
```

| 字段 | 值 |
|------|-----|
| asset_id | `asset_ffe79d915e4c` |
| kind | `card` |
| name | `a2_spin_shadow` |
| recipe | `a2_spin_shadow` |
| source（run） | `qdata-cli` |
| list 长度 | 7 |

run payload 原文：

```json
{
  "asset_id": "asset_ffe79d915e4c",
  "summary": {
    "schema": "stage1_a2_spin_v1",
    "n": 8,
    "shots": 8,
    "mae_shadow_features": 0.37420898055062574,
    "mae_classical_params_only": 0.03514637891139252,
    "phase_acc": 0.8333333333333334,
    "verdict_b3": "classical params competitive/better",
    "recipe": "a2_spin_shadow",
    "source": "qdata-cli"
  },
  "run_record_id": "run_c5e0d7bc2499"
}
```

## 不算什么

- **不算 G0**。没在 3080 填模型，没走「扫氢分子」。
- **不算 G2**。没有客户面回执演示。
- **不算接线 Pennylane**。Pennylane 仍只 reserved。
- 不算 HTTP `:8787` 已通。本包打的是 CLI `qdata run` 经 `invoke`，再读同一本地 store 卡片。
- 不算改了 [A-05_live.md](A-05_live.md) 的「未打 / 未证明」。

## 测

```bash
cd /Users/shl/nvidia/qagent
QAGENT_QDATA_HOME=/Users/shl/nvidia/qdata PYTHONPATH=src python3 tests/test_a05g.py
PYTHONPATH=src python3 tests/run_tests.py
```

没有该 `asset_id` 必须失败。skip 当绿 = 没做完。不 commit。未 commit。
