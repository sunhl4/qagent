# A-01 · qdata 诚实

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-26 |
| 角色 | S1 |
| 范围 | `qagent/src/qagent/adapters/qdata.py` · `qagent/tests/test_a01.py` |
| 未改 | `homes.py`（现有 `qdata_bin` / `qdata_url` 够用） |

## 行为

| 条件 | 结果 |
|------|------|
| `QAGENT_QDATA_URL` 已设且 HTTP 不通 | `submit_job` / `get_job` 抛 `RuntimeError`。不写本地假 job，不回 `status=done` |
| `get_job` 成功 | 只留 `status` / `summary` / `asset_id`。`_FORBIDDEN_OUT`（`bitstrings` / `rows` / `pauli_terms` / `counts_full` / `result_full`）从顶层和 summary 去掉 |
| 无 CLI、无 URL | `run_recipe` 仍走本地卡，`source=qagent-local-card`，出 `asset_id`。E01–E04 靠这条 |
| `QAGENT_QDATA_BIN` 已设但二进制失败 | 抛错，不退回本地卡假装做完 |
| 无 URL 的 `submit_job` | 合同 store 仍给 E03 用；`status` 是 `local-card`，不是 `done`。get 仍截断 |

不 `import qdata`。不发 `twin_id`。

## 测

```bash
cd qagent
PYTHONPATH=src python3 tests/test_a01.py
PYTHONPATH=src python3 tests/run_tests.py
```

环境在 `test_a01.py` 里隔离。死 URL 用 `http://127.0.0.1:1`。活 CLI / 活 `:8787` 另标 `live`，本包不跑。

## 剩

- 活 `qdata run` / 活 HTTP job 还没在本机打通。
- `homes.py` 没加 helper。
- `tests/run_tests.py` / `PROGRESS.md` 留给调度挂测。
