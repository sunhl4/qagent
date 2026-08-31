# A-02h · 落 qchem 卡

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | A-02h |
| 范围 | `qagent/src/qagent/adapters/qchem.py` · `qagent/tests/test_a02h.py` · 本笔记 |
| 未改 | `test_a02.py` · `test_a02g.py` · `test_a05g.py` · `qdata.py` · `run_tests.py` · `PROGRESS.md` · qchem 核 · workplace 密钥 · `chat.py` · `invoke.py` · `agent.py` |
| 状态 | 同一 `QAGENT_DATA_DIR`：活 `qchem_run`（`source=qchem-cli`）后 `qdata_list_assets` 含该 `asset_id`。≤20。无 Pauli / `twin_id`。**不算 G0**。skip 当绿 = 没做完 |

## 产品锁

- 完成线是同一隔离 store 上先 `qchem_run` 再 `list_assets` 见到该 `asset_id`。活 CLI 成功后写入现有 `qdata.json`（复用 `_db` / `_persist`），不新开第四套 store。
- 测里 `export QAGENT_QCHEM_HOME=/Users/shl/nvidia/qcchem-qml-md`。隔离 `QAGENT_DATA_DIR`（run 与 list 同一目录）。不 `apply_env()`。不读本机 `workplace.json`。不设 `QAGENT_QDATA_URL`。
- 不铸 `twin_id`。无 Pauli 全文。句柄只有 `circuit_id` / `asset_id` / `twin_id`，qchem 只许出 `asset_id`。目录最多 20 行。卡行键只有 `kind` / `name` / `asset_id` / `recipe`（跟现有 `_catalog_row`）。
- 无 HOME 仍走现有 local-wrap（`source=qagent-local-card`），不破坏 [A-02](A-02_qchem_honesty.md)。
- **不算 G0**。skip 当绿 = 没做完。列表没有该卡必须失败。

## 改了 qchem.py 哪几行

- import：`WiredQData` 旁复用 `_db` / `_persist`。
- 新增 `_persist_live_card`：活 payload 的 `asset_id` 写入同一 store 的 `assets`，`recipe` 取 scenario（本包是 `minimal_vqe`）。不把 Pauli / experiment 全文写进 list 行。
- `run`：活 CLI 成功后先 `_payload_from_live`，再 `_persist_live_card`，再返回原 payload。无 HOME 分支未改。

## 2026-08-27 真实 list 行

HOME：`QAGENT_QCHEM_HOME=/Users/shl/nvidia/qcchem-qml-md`（`.venv/bin/qchem-run` 能跑 `minimal_vqe`）。store 隔离在 `qagent/.qagent/test-a02h-store`。`QAGENT_QDATA_URL` 未设。不 `apply_env()`。不读 `workplace.json`。

调用（同一 `QAGENT_DATA_DIR`）：

```text
invoke("qchem_run", "lab", {"scenario": "minimal_vqe"})
invoke("qdata_list_assets", "lab", {})
```

run：`status=ok`。`payload.summary.source=qchem-cli`。有 `asset_id`。无 `twin_id`。

list：`status=ok`。`assets` 长度 7（≤20）。其中有一行带刚才的 `asset_id`。行键只有 `kind` / `name` / `asset_id` / `recipe`。无 Pauli / experiment 全文。无 `twin_id`。

抄到的目录行：

```json
{"kind": "card", "name": "minimal_vqe", "asset_id": "asset_4a4e6d27bc79", "recipe": "minimal_vqe"}
```

| 字段 | 值 |
|------|-----|
| asset_id | `asset_4a4e6d27bc79` |
| kind | `card` |
| name | `minimal_vqe` |
| recipe | `minimal_vqe` |
| source（run） | `qchem-cli` |
| list 长度 | 7 |

run payload 原文：

```json
{
  "asset_id": "asset_4a4e6d27bc79",
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
- 不算改了 [A-02](A-02_qchem_honesty.md) 的无 HOME local-wrap。
- 不算改了 [A-02g](A-02g_live_hit.md) 的活 CLI 打通合同。

## 测

```bash
cd /Users/shl/nvidia/qagent
export QAGENT_QCHEM_HOME=/Users/shl/nvidia/qcchem-qml-md
PYTHONPATH=src python3 tests/test_a02h.py
PYTHONPATH=src python3 tests/test_a02.py
PYTHONPATH=src python3 tests/test_a02g.py
PYTHONPATH=src python3 tests/run_tests.py
```

没有该 `asset_id` 必须失败。skip 当绿 = 没做完。不 commit。未 commit。
