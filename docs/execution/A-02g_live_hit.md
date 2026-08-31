# A-02g · 活 qchem 打通

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | A-02g |
| 范围 | `qagent/src/qagent/adapters/qchem.py` · `qagent/tests/test_a02g.py` · 本笔记 |
| 未改 | `test_a02.py` · `test_a02_live.py` · `A-02_live.md` · `run_tests.py` · `PROGRESS.md` · qchem 核 · workplace 密钥 · `chat.py` · `invoke.py` |
| 状态 | 真 `qchem-run --scenario minimal_vqe --json-summary` 经 `invoke("qchem_run")` 打通。`source=qchem-cli`。CLI 的 `experiment_id` 是 null，适配器在成功 CLI 后发 `asset_id`。不铸 `twin_id` / `circuit_id`。**不算 G0**。**不算 G2**。skip 当绿 = 没做完 |

## 改了哪一段

`_run_cli`：timeout 8 → 180（与 qdata CLI 对齐）。整段 `stdout` 不再 `json.loads`。新增 `_last_json_object`：纯 JSON（`test_a02` 假 CLI）仍整段解析；混有日志时抽出最后一段 JSON 对象。不 `apply_env()` 进 `invoke`。

`_payload_from_live` 未改合同：`experiment_id` 为 null 时用 `new_id("asset")`；`summary.source` 仍是 `qchem-cli`。不发 `twin_id` / `circuit_id`。

## 本机命令

```bash
export QAGENT_QCHEM_HOME=/Users/shl/nvidia/qcchem-qml-md
# .venv/bin/qchem-run --scenario minimal_vqe --json-summary
```

stdout 先打日志（含中间 `pipeline_events` JSON），最后一段才是 summary。CLI 原文：

```json
{
  "energy_after_variational": -1.1372759415451792,
  "energy_pauli_protocol": -1.1372759415451792,
  "experiment_id": null,
  "scf_energy": -1.116714325062552
}
```

无 `asset_id`。无 `twin_id`。

## 真实 invoke payload（抄）

`invoke("qchem_run", "lab", {"scenario": "minimal_vqe"})`，`status=ok`，`error=None`：

```json
{
  "asset_id": "asset_5f9f41afb311",
  "summary": {
    "energy_after_variational": -1.1372759415451792,
    "energy_pauli_protocol": -1.1372759415451792,
    "experiment_id": null,
    "scf_energy": -1.116714325062552,
    "source": "qchem-cli"
  }
}
```

抄到的 `asset_id`：`asset_5f9f41afb311`（随后 `test_a02g` 又一次 invoke 得到 `asset_fbc1019eed00`；`experiment_id` 每次都是 null，所以每次成功 CLI 后新发一个 `asset_id`）。`source=qchem-cli`。没有 `twin_id`。没有 `circuit_id`。

## 诚实

这是活 CLI 打通，不是 G0 / G2 过门。无 bin / 死 bin 仍归 [A-02](A-02_qchem_honesty.md)。[A-02_live.md](A-02_live.md) 的 skip 合同未改。不铸 `twin_id`。句柄只有 `circuit_id` / `asset_id` / `twin_id`，本包只出 `asset_id`。

## 测

```bash
cd /Users/shl/nvidia/qagent
export QAGENT_QCHEM_HOME=/Users/shl/nvidia/qcchem-qml-md
PYTHONPATH=src python3 tests/test_a02.py
PYTHONPATH=src python3 tests/test_a02g.py
PYTHONPATH=src python3 tests/run_tests.py
```

`test_a02` 假 CLI 纯 JSON 必须仍绿。`test_a02g` 真 invoke；skip 当绿 = 没做完。未 commit。
