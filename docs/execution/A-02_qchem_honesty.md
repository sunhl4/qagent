# A-02 · qchem 诚实

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-26 |
| 角色 | S2 |
| 范围 | `qagent/src/qagent/adapters/qchem.py` · `qagent/src/qagent/adapters/homes.py`（`qchem_bin_requested` / `qchem_parity_bin_requested`）· `qagent/tests/test_a02.py` |
| 未改 | `qdata.py` · `run_tests.py` · `PROGRESS.md` · `chat.py` · `dsh_session.py` |

## 行为

| 条件 | 结果 |
|------|------|
| 无 `QAGENT_QCHEM_BIN` / `QAGENT_QCHEM_HOME` | `qchem_run` 走本地卡，`source=qagent-local-card`，出 `asset_id`。不写 `qchem-cli`，不写 `done-on-machine` |
| `QAGENT_QCHEM_BIN` 或 HOME 指向缺失/失败二进制 | 抛 `RuntimeError`。不退回本地卡，不标 `source=qchem-cli` |
| 活 CLI 成功 | 只出 `asset_id` + `summary`（`source=qchem-cli`）。不发 `twin_id`。电路体 / `circuit_id` 不当句柄；电路只经后续 pin |
| `export_parity` | 必须带 `asset_id`。parity bin 指向缺失/失败则抛错；无 bin 仍给本地 `table_id` |

不 `import qchem`。不发 `twin_id`。

## 测

```bash
cd qagent
PYTHONPATH=src python3 tests/test_a02.py
PYTHONPATH=src python3 tests/run_tests.py
```

环境在 `test_a02.py` 里隔离。死 bin 用 `/no/such/qagent-qchem-bin`。活 CLI 用临时假脚本，本包不打真 `qchem-run`。

## 剩

- 真机 `qchem-run --scenario minimal_vqe --json-summary` 还没在本机打通（仓里有 `/Users/shl/nvidia/qcchem-qml-md/.venv/bin/qchem-run`，但未设 `QAGENT_QCHEM_HOME`）。
- `homes.py` 加了 requested 两个 helper：HOME 指空目录时也能诚实失败；`qchem_bin()` 仍只在文件存在时返回，health 不谎报 live。
- `tests/run_tests.py` / `PROGRESS.md` 留给调度挂测。
