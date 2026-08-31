# A-03i · vibe_path TwinRun 改用 pipeline

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | S2 · A-03i |
| 范围 | `qagent/src/qagent/services/vibe_path.py` · 本笔记 · `qagent/tests/test_a03i.py` |
| 未改 | `assignment.py` · `eval_run.py` · `test_e05g.py` · `test_a03g.py` · `test_q01.py` · `run_tests.py` · `PROGRESS.md` · `chat.py` · `adapters/ionstack.py` · `agent.py` · ionstack 核 · workplace 密钥 · CAL / shuttle |
| 状态 | `run_vibe_path` 的 TwinRun 默认 `mode=pipeline`。未批准仍 `needs_ask`、无 `twin_id`。`QAGENT_TWIN_URL=http://127.0.0.1:8765` 且 `approved=True` 时黄金路径 ok，handles 有 TwinRun `twin_id` + 该步 `provenance=qccd-twin`。死 URL（`:1`）仍诚实 error、无假 `twin_id`。**不要 signoff**。**CAL 不进工具**。**不算 G0**。**不算 G1**。未 commit。 |

## 产品锁

- 完成线是黄金路径 `run_vibe_path(..., approved=True)` 走 **pipeline TwinRun**，不是 `mode=signoff`。
- `mode=signoff` 的 TwinRun HTTP 400：`signoff mode requires calibration`。不为了过门把 CAL / shuttle 塞进工具或请求。
- **只有** ionstack TwinRun 能发 `twin_id`。本包不铸本地 `twin_id`。死 URL 诚实 error，handles 无 `twin_id`。
- 未批准必须仍 `needs_ask`。批准后同一工具名续跑，才会出现 `twin_id`。
- 测里活路 `export QAGENT_TWIN_URL=http://127.0.0.1:8765`。
- **不算 G0 / G1**。没在 3080 填模型，没走「扫氢分子」，没把演示门标绿。
- skip 当绿 = 没做完。不编 `accepted:true`。未 commit。

## vibe_path 改了什么

只改 TwinRun 默认 `mode`：`signoff` → `pipeline`。`shots` 与 `circuit=DEFAULT_CIRCUIT` 不动。请求体仍只有 `mode` / `shots` / `circuit` / `circuit_id`。没有 `calibration` / `cal` / `shuttle`。

```python
twin = invoke(
    "ionstack_twin_run",
    preset,
    {
        "mode": "pipeline",
        "shots": shots,
        "circuit": DEFAULT_CIRCUIT,
        "circuit_id": handles.get("circuit_id"),
    },
    approved=approved,
)
```

A-03h 已把 E05 `_twin_args` 改成 pipeline。本包对齐黄金路径，不改评测、不改交办。

## 2026-08-27 活 vibe_path

调度已起 `:8765`。本轮未改 adapter。未 commit。

### 1. `mode=signoff` 仍 400（不为过门塞 CAL）

```json
{"error": "signoff mode requires calibration"}
```

### 2. `run_vibe_path("lab", shots=8, approved=True)` · `mode=pipeline`

结果：`status=ok`。handles 有真 `twin_id`。TwinRun 步 `provenance=qccd-twin`。有 `counts`。不要 signoff。

抄到的句柄：

| 字段 | 值 |
|------|-----|
| twin_id | `5c9ce47cda91d673598ba1283fed4e5ab4c1c17d2c770245ecab2534e3e071a5` |
| provenance | `qccd-twin` |

没有真 TwinRun `twin_id` 就失败。skip 当绿 = 没做完。

### 3. 未批准仍 ask

`approved=False` → `status=needs_ask`，`tool=ionstack_twin_run`，handles 无 `twin_id`。

### 4. 死 URL 仍诚实 error

`QAGENT_TWIN_URL=http://127.0.0.1:1` 且 `approved=True`：`status=error`，不铸 `twin_id`。

## 不算什么

- **不算 G0**。没在 3080 填模型，没走「扫氢分子」。
- **不算 G1**。黄金路径默认对齐了，演示门仍要人走清单。
- 不算 `mode=signoff` 已通。signoff 要 CAL；CAL 不进工具。
- 未改 `assignment.py`（交办 ask / 批准续跑是 R-03g）。
- 未改 `adapters/ionstack.py`。未改 `test_q01.py` / `test_e05g.py`。未 commit。

## 测

```bash
cd /Users/shl/nvidia/qagent
QAGENT_TWIN_URL=http://127.0.0.1:8765 PYTHONPATH=src python3 tests/test_a03i.py
PYTHONPATH=src python3 tests/run_tests.py
```

没有真 TwinRun `twin_id` 必须失败。skip 当绿 = 没做完。不 commit。
