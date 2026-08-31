# A-03h · E05 评测改用 pipeline TwinRun

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | S2 · A-03h |
| 范围 | `qagent/src/qagent/services/eval_run.py` · 本笔记 · `qagent/tests/test_e05g.py` |
| 未改 | `test_q01.py` · `test_a03c.py` · `test_a03g.py` · `run_tests.py` · `PROGRESS.md` · `chat.py` · `adapters/ionstack.py` · `agent.py` · ionstack 核 · workplace 密钥 · CAL / shuttle |
| 状态 | `_twin_args` 默认 `mode=pipeline`。`QAGENT_TWIN_URL=http://127.0.0.1:8765` 时 `run_eval(E05)` ok，payload 有 TwinRun `twin_id` + `counts` + `provenance=qccd-twin`。死 URL（`:1`）仍诚实 error、无假 `twin_id`。**不要 signoff**。**CAL 不进工具**。**不算 G0**。**不算 G3**。未 commit。 |

## 产品锁

- 完成线是 `run_eval(E05)` 走 `_twin_args` 的 **pipeline TwinRun**，不是 `mode=signoff`。
- `mode=signoff` 的 TwinRun HTTP 400：`signoff mode requires calibration`。不为了过门把 CAL / shuttle 塞进工具或请求。
- **只有** ionstack TwinRun 能发 `twin_id`。本包不铸本地 `twin_id`。死 URL 诚实 error，payload 无 `twin_id`。
- 测里活路 `export QAGENT_TWIN_URL=http://127.0.0.1:8765`。suite 把 Twin URL 隔到 `http://127.0.0.1:1`，现有 E 条 / product_eval 仍走诚实 error。
- **不算 G0 / G3**。没在 3080 填模型，没走「扫氢分子」。
- skip 当绿 = 没做完。不编 `accepted:true`。未 commit。

## `_twin_args` 改了什么

只改默认 `mode`：`signoff` → `pipeline`。`shots=1000` 与 `circuit=DEFAULT_CIRCUIT` 不动。请求体仍只有 `mode` / `shots` / `circuit`。没有 `calibration` / `cal` / `shuttle`。

```python
body = {"mode": "pipeline", "shots": 1000, "circuit": DEFAULT_CIRCUIT}
```

E05 仍 `invoke("ionstack_twin_run", preset, _twin_args(), approved=True)`。E21 仍未批准，只看到 ask。

## 2026-08-27 活 E05

HOME：`QAGENT_IONSTACK_HOME=/Users/shl/Q-software`。调度已起 `:8765`。本轮未改 adapter。未 commit。

### 1. `mode=signoff` 仍 400（不为过门塞 CAL）

```json
{"error": "signoff mode requires calibration"}
```

`http_code=400`

### 2. `run_eval(E05)` · `_twin_args` `mode=pipeline` · `QAGENT_TWIN_URL=http://127.0.0.1:8765`

调用：

```text
run_eval(E05)  # ionstack_twin_run + _twin_args() + approved=True
# _twin_args() == {"mode": "pipeline", "shots": 1000, "circuit": DEFAULT_CIRCUIT}
```

结果：`EvalResult(id='E05', ok=True)`。`status=ok`。有真 `twin_id`。`provenance=qccd-twin`。有 `counts`。不要 signoff。

抄到的句柄与摘要：

| 字段 | 值 |
|------|-----|
| twin_id | `5c9ce47cda91d673598ba1283fed4e5ab4c1c17d2c770245ecab2534e3e071a5` |
| provenance | `qccd-twin` |
| shots_actual | 1000 |
| counts | `{"11": 506, "00": 494}` |

payload 原文：

```json
{
  "counts": {
    "11": 506,
    "00": 494
  },
  "provenance": "qccd-twin",
  "shots_actual": 1000,
  "twin_id": "5c9ce47cda91d673598ba1283fed4e5ab4c1c17d2c770245ecab2534e3e071a5"
}
```

没有真 TwinRun `twin_id` 就失败。skip 当绿 = 没做完。

### 3. 死 URL 仍诚实 error

`QAGENT_TWIN_URL=http://127.0.0.1:1` 时 E05 仍走 `twin_run_live_or_honest_error`：`status=error`，不铸 `twin_id`。`run_eval(E05)` 因此仍 ok。suite / `QAGENT_DSH_MUX=0` 总跑把 Twin 隔到 `:1`，现有 E 条绿。

## 不算什么

- **不算 G0**。没在 3080 填模型，没走「扫氢分子」。
- **不算 G3**。
- 不算 `mode=signoff` 已通。signoff 要 CAL；CAL 不进工具。
- 不算改了 [A-03g_live_hit.md](A-03g_live_hit.md) / [A-03_live.md](A-03_live.md)。
- 未改 `adapters/ionstack.py`。未改 `test_q01.py` / `test_a03c.py` / `test_a03g.py`。未 commit。

## 测

```bash
cd /Users/shl/nvidia/qagent
QAGENT_TWIN_URL=http://127.0.0.1:8765 PYTHONPATH=src python3 tests/test_e05g.py
PYTHONPATH=src python3 tests/run_tests.py
```

没有真 TwinRun `twin_id` 必须失败。skip 当绿 = 没做完。不 commit。
