# A-01j · 活 get_run_record

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | S1 · A-01j |
| 范围 | 只本笔记 + `qagent/tests/test_a01j.py` |
| 未改 | `qagent/src/**` · `test_a01g.py` · `test_a05g.py` · `A-01_live.md` · `run_tests.py` · `PROGRESS.md` · customer-shell · `chat.py` · qdata 核 · workplace 密钥 |
| 状态 | 同一 `QAGENT_DATA_DIR`：先 `invoke("qdata_run_recipe")` 打到 `source=qdata-cli` + `asset_id` + `run_record_id`，再 `invoke("qdata_get_run_record")` 读同一本地 store。同一 `asset_id` / `run_record_id`。有 `summary`。无 `twin_id`。**不算 G0**。**不算 G2**。**不算接线 Pennylane**。 |

## 产品锁

- 完成线是同一隔离 store 上先 `run_recipe`（`qdata-cli`）再 `get_run_record` 见到同一 `asset_id` / `run_record_id`，不是 raw `qdata` 子命令。
- `get_run_record` 读同一 `QAGENT_DATA_DIR` 的本地 store。不铸 `twin_id`。无 Pauli 全文。句柄只有 `circuit_id` / `asset_id` / `twin_id`，qdata 只许出 `asset_id`。
- 测里 `export QAGENT_QDATA_HOME=/Users/shl/nvidia/qdata`。隔离 `QAGENT_DATA_DIR`（run 与 get 同一目录）。不 `apply_env()`。不读本机 `workplace.json`。不设 `QAGENT_QDATA_URL`（本包打 CLI 卡再读本地 record，不是 HTTP job）。
- 旧 [A-01_live.md](A-01_live.md) 的「未打 / 未证明」合同不动。那条是 gated skip 探活，不是本包。
- **不算 G0 / G2**。**不算接线 Pennylane**。Pennylane 仍 reserved。
- skip 当绿 = 没做完。没有 `run_record` 或 `asset_id` 对不上必须失败。

## 2026-08-27 真实 get_run_record payload

HOME：`QAGENT_QDATA_HOME=/Users/shl/nvidia/qdata`（`.venv/bin/qdata` 有 `run`）。store 隔离在 `qagent/.qagent/test-a01j-store`。`QAGENT_QDATA_URL` 未设。不 `apply_env()`。不读 `workplace.json`。

调用（同一 `QAGENT_DATA_DIR`）：

```text
invoke("qdata_run_recipe", "lab", {"name": "a2_spin_shadow", "shots": 8})
invoke("qdata_get_run_record", "lab", {"run_record_id": "<run 的 run_record_id>"})
```

run：`status=ok`。`payload.summary.source=qdata-cli`。有 `asset_id`。有 `run_record_id`。无 `twin_id`。

get：`status=ok`。同一 `run_record_id`。同一 `asset_id`。有 `summary`。无 `twin_id`。无 Pauli 全文。

抄到的句柄：

| 字段 | 值 |
|------|-----|
| asset_id | `asset_d89d7c24c9a1` |
| run_record_id | `run_342966063a97` |
| source（run / record） | `qdata-cli` |
| recipe | `a2_spin_shadow` |

get_run_record payload 原文：

```json
{
  "run_record_id": "run_342966063a97",
  "summary": {
    "recipe": "a2_spin_shadow",
    "source": "qdata-cli"
  },
  "asset_id": "asset_d89d7c24c9a1"
}
```

## 不算什么

- **不算 G0**。没在 3080 填模型，没走「扫氢分子」。
- **不算 G2**。没有客户面回执演示。
- **不算接线 Pennylane**。Pennylane 仍只 reserved。
- 不算 HTTP `:8787` 已通。本包打的是 CLI `qdata run` 经 `invoke`，再读同一本地 store 的 `run_record`。
- 不算改了 [A-01_live.md](A-01_live.md) 的「未打 / 未证明」。

## 测

```bash
cd /Users/shl/nvidia/qagent
QAGENT_QDATA_HOME=/Users/shl/nvidia/qdata PYTHONPATH=src python3 tests/test_a01j.py
PYTHONPATH=src python3 tests/run_tests.py
```

没有 `run_record` 或 `asset_id` 对不上必须失败。skip 当绿 = 没做完。不 commit。未 commit。
