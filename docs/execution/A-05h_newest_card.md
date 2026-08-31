# A-05h · 最新卡不被挤

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | S1 · A-05h |
| 范围 | `qagent/src/qagent/adapters/qdata.py` · 本笔记 · `qagent/tests/test_a05h.py` |
| 未改 | `test_a05.py` · `test_a05g.py` · `run_tests.py` · `PROGRESS.md` · `agent.py` · customer-shell · `chat.py` · qdata 核 |
| 状态 | store 旧卡超过预算时，`invoke("qdata_run_recipe")` 刚写出的 `asset_id` 仍在 `qdata_list_assets`。总长 ≤20。无 Pauli / `twin_id`。**不算 G0**。 |

## 产品锁

- 完成线是超预算后列表仍含刚 `run_recipe` 的 `asset_id`，不是把 cap 调大，也不是 skip 当绿。
- 测里隔离 `QAGENT_DATA_DIR`。先种 25 张旧卡，再 `invoke("qdata_run_recipe", "lab", {"name": "a2_spin_shadow", "shots": 8})`，再 `invoke("qdata_list_assets")`。无 `QAGENT_QDATA_HOME` 时走本地卡（`source=qagent-local-card`）。
- 不铸 `twin_id`。无 Pauli 全文。无 bitstrings / OPENQASM。句柄只有 `circuit_id` / `asset_id` / `twin_id`，qdata 只许出 `asset_id`。目录最多 20 行。
- **不算 G0**。没在 3080 填模型，没走「扫氢分子」。
- skip 当绿 = 没做完。没有该 `asset_id` 必须失败。

## 改了 `_card_rows` 哪几行

`qagent/src/qagent/adapters/qdata.py`：

- **117–128** `_card_rows`。原先按 dict 从头取 `limit` 张（`if len(rows) >= limit: break`），超预算时只剩最旧的前 N 张。
- **120** 改为 `items = list(assets.items())[-limit:] if limit > 0 else []`，按 Python 3.7+ 插入序取**末尾** `limit` 张（最新）。`limit <= 0` 不能写 `[-0:]`（那会整表返回）。
- 行键仍是 `kind` / `name` / `asset_id` / `recipe`。`list_assets` 仍是 recipe + cards + knowledge，最后 `[:20]`。

`save_json` 带 `sort_keys=True`，reload 后插入序会变成键排序，刚写入的 `asset_<hex>` 可能排到 `asset_old_*` 前面，末尾切片仍会挤掉新卡。所以 **60–63** `_persist` 改为不排序落盘，插入序才能活过 reload。`_persist` 不再调用 `save_json`。

## 2026-08-27 真实 list（含新卡）

隔离 store：`qagent/.qagent/test-a05h-store`。`QAGENT_QDATA_HOME` / `QAGENT_QDATA_URL` 未设。先种 `asset_old_00` … `asset_old_24`，再：

```text
invoke("qdata_run_recipe", "lab", {"name": "a2_spin_shadow", "shots": 8})
invoke("qdata_list_assets", "lab", {})
```

run：`status=ok`。`payload.summary.source=qagent-local-card`。有 `asset_id`。无 `twin_id`。

list：`status=ok`。`assets` 长度 20（≤20）。含刚才的新卡。最旧的 `asset_old_00` 被挤掉。行键只有 `kind` / `name` / `asset_id` / `recipe`。无 Pauli / bitstrings / OPENQASM。无 `twin_id`。

抄到的新卡行：

```json
{"kind": "card", "name": "a2_spin_shadow", "asset_id": "asset_77f2d9d5757a", "recipe": "a2_spin_shadow"}
```

真实 list 全文（20 行）：

```json
[{"kind": "recipe", "name": "a1_closed_loop", "recipe": "a1_closed_loop"}, {"kind": "recipe", "name": "a2_spin_shadow", "recipe": "a2_spin_shadow"}, {"kind": "recipe", "name": "a2_chem_pes", "recipe": "a2_chem_pes"}, {"kind": "recipe", "name": "a3_sensitivity", "recipe": "a3_sensitivity"}, {"kind": "recipe", "name": "qem_triad", "recipe": "qem_triad"}, {"kind": "card", "name": "a2_chem_pes", "asset_id": "asset_old_12", "recipe": "a2_chem_pes"}, {"kind": "card", "name": "a2_chem_pes", "asset_id": "asset_old_13", "recipe": "a2_chem_pes"}, {"kind": "card", "name": "a2_chem_pes", "asset_id": "asset_old_14", "recipe": "a2_chem_pes"}, {"kind": "card", "name": "a2_chem_pes", "asset_id": "asset_old_15", "recipe": "a2_chem_pes"}, {"kind": "card", "name": "a2_chem_pes", "asset_id": "asset_old_16", "recipe": "a2_chem_pes"}, {"kind": "card", "name": "a2_chem_pes", "asset_id": "asset_old_17", "recipe": "a2_chem_pes"}, {"kind": "card", "name": "a2_chem_pes", "asset_id": "asset_old_18", "recipe": "a2_chem_pes"}, {"kind": "card", "name": "a2_chem_pes", "asset_id": "asset_old_19", "recipe": "a2_chem_pes"}, {"kind": "card", "name": "a2_chem_pes", "asset_id": "asset_old_20", "recipe": "a2_chem_pes"}, {"kind": "card", "name": "a2_chem_pes", "asset_id": "asset_old_21", "recipe": "a2_chem_pes"}, {"kind": "card", "name": "a2_chem_pes", "asset_id": "asset_old_22", "recipe": "a2_chem_pes"}, {"kind": "card", "name": "a2_chem_pes", "asset_id": "asset_old_23", "recipe": "a2_chem_pes"}, {"kind": "card", "name": "a2_chem_pes", "asset_id": "asset_old_24", "recipe": "a2_chem_pes"}, {"kind": "card", "name": "a2_spin_shadow", "asset_id": "asset_77f2d9d5757a", "recipe": "a2_spin_shadow"}, {"kind": "knowledge", "name": "twin_run.md"}]
```

| 字段 | 值 |
|------|-----|
| asset_id | `asset_77f2d9d5757a` |
| kind | `card` |
| name | `a2_spin_shadow` |
| recipe | `a2_spin_shadow` |
| source（run） | `qagent-local-card` |
| list 长度 | 20 |

## 不算什么

- **不算 G0**。没填模型，没走演示剧本。
- 不算改了 `test_a05.py` / `test_a05g.py` 的合同。
- 不算接线 Pennylane。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_a05h.py
PYTHONPATH=src python3 tests/test_a05.py
PYTHONPATH=src python3 tests/test_a05g.py
PYTHONPATH=src python3 tests/run_tests.py
```

没有该 `asset_id` 必须失败。skip 当绿 = 没做完。不 commit。未 commit。
