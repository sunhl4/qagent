# A-01g · 活 qdata invoke 打通

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | S1 · A-01g |
| 范围 | 只本笔记 + `qagent/tests/test_a01g.py` |
| 未改 | `qagent/src/**` · `test_a01.py` · `test_a01_live.py` · `A-01_live.md` · `run_tests.py` · `PROGRESS.md` · customer-shell · `chat.py` · qdata 核 · workplace 密钥 |
| 状态 | `invoke("qdata_run_recipe")` 已打到 `source=qdata-cli` + `asset_id`。**不算 G0**。**不算 G2**。**不算接线 Pennylane**。 |

## 产品锁

- 完成线是 `invoke`，不是 raw `qdata run` stdout 含 `asset_id`。
- CLI 自己的 stdout JSON **没有** `asset_id` 字段。句柄是适配器从成功 CLI 收的。
- 不铸 `twin_id`。无 circuit body。句柄只有 `circuit_id` / `asset_id` / `twin_id`，qdata 只许出 `asset_id`。
- 测里 `export QAGENT_QDATA_HOME=/Users/shl/nvidia/qdata`。不 `apply_env()`。不读本机 `workplace.json`。
- 旧 [A-01_live.md](A-01_live.md) 的「未打 / 未证明」合同不动。那条是 gated skip 探活，不是本包。
- **不算 G0 / G2**。**不算接线 Pennylane**。Pennylane 仍 reserved。

## 2026-08-27 真实 payload

HOME：`QAGENT_QDATA_HOME=/Users/shl/nvidia/qdata`（`.venv/bin/qdata` 有 `run`）。store 隔离在 `qagent/.qagent/test-a01g-store`。

调用：

```text
invoke("qdata_run_recipe", "lab", {"name": "a2_spin_shadow", "shots": 8})
```

结果：`status=ok`。`payload.summary.source=qdata-cli`。有 `asset_id`。无 `twin_id`。无 circuit body。

抄到的句柄与摘要：

| 字段 | 值 |
|------|-----|
| asset_id | `asset_182483a482ba` |
| source | `qdata-cli` |
| recipe | `a2_spin_shadow` |
| shots | 8 |

payload 原文：

```json
{
  "asset_id": "asset_182483a482ba",
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
  "run_record_id": "run_76d9446914b7"
}
```

## 不算什么

- **不算 G0**。没在 3080 填模型，没走「扫氢分子」。
- **不算 G2**。没有客户面回执演示。
- **不算接线 Pennylane**。Pennylane 仍只 reserved。
- 不算 HTTP `:8787` 已通。本包打的是 CLI `qdata run` 经 `invoke`。
- 不算改了 [A-01_live.md](A-01_live.md) 的「未打 / 未证明」。

## 测

```bash
cd /Users/shl/nvidia/qagent
QAGENT_QDATA_HOME=/Users/shl/nvidia/qdata PYTHONPATH=src python3 tests/test_a01g.py
PYTHONPATH=src python3 tests/run_tests.py
```

没有活 `asset_id` 必须失败。skip 当绿 = 没做完。不 commit。
