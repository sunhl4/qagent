# R-03g · 活交办批准签收回执

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | S2 · R-03g |
| 范围 | `qagent/src/qagent/services/assignment.py` · 本笔记 · `qagent/tests/test_r03g.py` |
| 未改 | `vibe_path.py` · `eval_run.py` · `models/assignment.py`（`can_sign` / 回执合同不动） · `test_r03.py` · `test_r03c.py` · `run_tests.py` · `PROGRESS.md` · `chat.py` · `adapters/ionstack.py` · `agent.py` · ionstack 核 · workplace 密钥 · CAL / shuttle |
| 状态 | 交办 TwinRun ask / `_run_sign` 默认 `mode=pipeline`。未批准仍 `needs_ask`，ask.args.mode=`pipeline`，回执 `signed=false`。活 Twin `:8765` 上 `create` → `run` → `approve` 后 `status=signed`，回执 `signed=true`，有 TwinRun `twin_id` + sources 含 `qccd-twin`。死 URL 批准失败、不铸 `twin_id`、回执仍未签。**不要 signoff**。**CAL 不进工具**。**不算 G0**。**不算 G2**。未 commit。 |

## 产品锁

- 完成线是活交办：人批之后 `receipt.signed` 为真，当且仅当有 TwinRun `twin_id` 且 sources 含 `qccd-twin`。`can_sign` 合同不改。
- G2 批准走 `_resume(ask.args)`。ask 里若仍写 `mode=signoff`，活 `ionstack_twin_run` HTTP 400：`signoff mode requires calibration`。不为过门把 CAL / shuttle 塞进工具。
- **只有** ionstack TwinRun 能发 `twin_id`。本包不铸本地 `twin_id`。死 URL 诚实失败，回执 `signed=false`。
- 未批准必须仍 `needs_ask`。lane 名 `signoff`（阶段）不动；改的是 TwinRun **mode**。
- **不算 G0 / G2**。没在 3080 填模型，没让客户点「批准上机」走完整演示。
- skip 当绿 = 没做完。不编 `accepted:true`。未 commit。

## assignment 改了什么

三处 TwinRun `mode`：`signoff` → `pipeline`。

1. `_run_lab` 未批准时写入的 `ask.args.mode`
2. `_run_sign` 实际 `invoke` 的 `mode`
3. `_run_sign` 未批准时写入的 `ask.args.mode`

`shots` 与 `circuit=DEFAULT_CIRCUIT` 不动。没有 `calibration` / `cal` / `shuttle`。`approve()` 仍先 `_resume(ask)`；ask 已是 pipeline，续跑不再打 signoff。

A-03h / A-03i 分别改了评测默认和黄金路径默认。本包只改交办。

## 2026-08-27 活回执

调度已起 `:8765`。本轮未改 adapter、未改 `can_sign`。未 commit。

### 1. `mode=signoff` 仍 400（不为过门塞 CAL）

```json
{"error": "signoff mode requires calibration"}
```

### 2. lab `create` → `run(approved=False)` → `approve()`

未批准：`status=needs_ask`，`ask.args.mode=pipeline`，回执 `signed=false`。

批准后：`status=signed`。回执 `signed=true`。有真 `twin_id`。sources 含 `qccd-twin`。

抄到的句柄：

| 字段 | 值 |
|------|-----|
| twin_id | `5c9ce47cda91d673598ba1283fed4e5ab4c1c17d2c770245ecab2534e3e071a5` |
| sources | 含 `qccd-twin` |
| signed | true |

没有真 TwinRun `twin_id` 就失败。skip 当绿 = 没做完。

### 3. 死 URL 批准仍未签

`QAGENT_TWIN_URL=http://127.0.0.1:1`：未批准仍 ask；批准 `status=failed`，无 `twin_id`，回执 `signed=false`。

## 不算什么

- **不算 G0**。没在 3080 填模型，没走「扫氢分子」。
- **不算 G2**。这是服务层交办批准，不是客户脸点批准上机。
- 不算 `mode=signoff` 已通。signoff 要 CAL；CAL 不进工具。
- 未改 `vibe_path.py`（黄金路径是 A-03i）。
- 未改 `models/assignment.py`。未改 `test_r03.py` / `test_r03c.py`。未 commit。

## 测

```bash
cd /Users/shl/nvidia/qagent
QAGENT_TWIN_URL=http://127.0.0.1:8765 PYTHONPATH=src python3 tests/test_r03g.py
PYTHONPATH=src python3 tests/run_tests.py
```

没有真 TwinRun `twin_id` 必须失败。skip 当绿 = 没做完。不 commit。
