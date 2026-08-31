# A-05i · 活目录打 `GET /v1/assets`

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | S1 · A-05i |
| 范围 | `qagent/src/qagent/adapters/qdata.py` · 本笔记 · `qagent/tests/test_a05i.py` |
| 未改 | `test_a05.py` · `test_a05g.py` · `test_a05h.py` · `A-05_live.md` · `run_tests.py` · `PROGRESS.md` · customer-shell · `chat.py` · qdata 核 · workplace 密钥 |
| 状态 | 设了 `QAGENT_QDATA_URL` 时 `invoke("qdata_list_assets")` 打活 `GET /v1/assets`，短行进目录。死 URL 诚实失败。≤20。无 Pauli / `twin_id`。**不算 G0**。**不算 G2**。**不算接线 Pennylane**。未 commit。 |

## 产品锁

- 完成线是活 HTTP 资产出现在目录短行里，不是再记一遍 skip。
- 测里隔离 `QAGENT_DATA_DIR`。不 `apply_env()`。不读本机 `workplace.json`。
- 无 URL 时仍只读本地 store（A-05g / A-05h 不动）。
- 有 URL 则 `GET {url}/v1/assets`。回的必须是列表。胖字段不进目录行。行键只有 `kind` / `name` / `asset_id` / `recipe`。
- 死 URL 必须失败，不许空转成本地绿。
- 不铸 `twin_id`。目录最多 20 行。句柄只有 `circuit_id` / `asset_id` / `twin_id`，本工具只许出 `asset_id`。
- **不算 G0 / G2**。**不算接线 Pennylane**。Pennylane 仍 reserved。
- skip 当绿 = 没做完。没有该 `asset_id` 必须失败。

## 2026-08-27 真实 HTTP 行

`:8787` healthz `status=ok`。先 `POST /v1/jobs/sample-to-solver`（`provider=chem.h2_sto3g`），job 完成后 `GET /v1/assets` 有：

```json
{"asset_id": "209528abb69468e9041518ee7f8fc4dc4ddc97eb62dfedbf771a664fd4ef7170", "kind": "bitstrings", "created_utc": "2026-08-26T21:19:16Z"}
```

`invoke("qdata_list_assets")` 且 `QAGENT_QDATA_URL=http://127.0.0.1:8787` 时，目录含该 `asset_id`，短行：

```json
{"kind": "card", "name": "bitstrings", "asset_id": "209528abb69468e9041518ee7f8fc4dc4ddc97eb62dfedbf771a664fd4ef7170"}
```

无 Pauli / bitstrings 全文 / OPENQASM。无 `twin_id`。列表长度 7（≤20）。

## 不算什么

- **不算 G0**。没在 3080 填模型，没走「扫氢分子」。
- **不算 G2**。没有客户面回执演示。
- **不算接线 Pennylane**。
- 不算改了 [A-05_live.md](A-05_live.md) 的「未打 / 未证明」。
- 未 commit。不 `apply_env()`。

## 测

```bash
cd /Users/shl/nvidia/qagent
QAGENT_DSH_MUX=0 PYTHONPATH=src python3 tests/test_a05i.py
PYTHONPATH=src python3 tests/run_tests.py
```

没有该 `asset_id` 必须失败。skip 当绿 = 没做完。不 commit。
