# A-03g · 活 Twin pipeline TwinRun 打通

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | S2 · A-03g |
| 范围 | 只本笔记 + `qagent/tests/test_a03g.py` |
| 未改 | `qagent/src/**`（含 `adapters/ionstack.py`）· `test_a03c.py` · `test_a03_live.py` · `A-03_live.md` · `run_tests.py` · `PROGRESS.md` · `chat.py` · ionstack 核 · workplace 密钥 |
| 状态 | `invoke("ionstack_twin_identity")` `live=true` 且 payload **无** `twin_id`；`invoke("ionstack_twin_run")` `mode=pipeline` 已打到真 `twin_id` + `provenance=qccd-twin` + `counts`。**identity 单独不算已通**。这次是 **pipeline TwinRun 才算**。**不算 G0**。**不算 G2**。**不算接线 Pennylane**。未 commit。 |

## 产品锁

- 完成线是 `invoke("ionstack_twin_run")` 的 **pipeline TwinRun**，不是 `GET /v1/twin/identity`，也不是 `invoke("ionstack_twin_identity")`。identity 单独不算已通。
- 原始 HTTP identity 可能带 `twin_id`。`invoke("ionstack_twin_identity")` 只许回 `preset` / `n_qubits` / `live`，**payload 不许有 `twin_id`**。
- **只有** ionstack TwinRun 能发 `twin_id`。本包不铸本地 `twin_id`。不把 identity HTTP 里的字段当成已签收。
- **不要 signoff**。`mode=signoff` 的 TwinRun HTTP 400：`signoff mode requires calibration`。不为了过门把 CAL / shuttle 塞进工具或请求。
- 测里 `export QAGENT_TWIN_URL=http://127.0.0.1:8765`。不 `apply_env()`。不读本机 `workplace.json`。
- 旧 [A-03_live.md](A-03_live.md) 的「未打 / 未证明」合同不动。那条是 gated skip 探活，不是本包。
- **不算 G0 / G2**。**不算接线 Pennylane**。Pennylane 仍 reserved。
- 不编 `accepted:true`。不换 `circuit_id`。未改 adapter。

## 2026-08-27 本轮再打（调度冒烟必须自己再打一遍）

HOME：`QAGENT_IONSTACK_HOME=/Users/shl/Q-software`。`ionstack-serve` 在仓根 `.venv/bin/ionstack-serve`。调度已起 `:8765`。本轮 **未** `pkill dsh`，**未**杀 3081。未改 adapter。未 commit。

### 1. `GET /v1/twin/identity` 200

`preset=t_junction`。原始 HTTP **带** `twin_id`。这不算已通。

```json
{"schema": "ionstack_twin_run", "schema_version": "2", "package_version": "10.0.0", "twin_id": "5c9ce47cda91d673598ba1283fed4e5ab4c1c17d2c770245ecab2534e3e071a5", "preset": "t_junction", "calibration_snapshot_id": null, "n_qubits": 2}
```

`http_code=200`

### 2. `invoke("ionstack_twin_identity")`

`status=ok`。`live=true`。payload **无** `twin_id`。只留 `preset` / `n_qubits` / `live`。identity 单独不算已通。

```json
{
  "live": true,
  "n_qubits": 2,
  "preset": "t_junction"
}
```

### 3. `mode=signoff` TwinRun HTTP 400

不为过门塞 CAL。CAL / shuttle 永不进工具。

```json
{"error": "signoff mode requires calibration"}
```

`http_code=400`

### 4. `invoke("ionstack_twin_run")` · `mode=pipeline` · `approved=True`

调用：

```text
invoke("ionstack_twin_run", "lab", {"mode": "pipeline", "shots": 8, "circuit": eval_run.DEFAULT_CIRCUIT}, approved=True)
```

结果：`status=ok`。`decision=ask`（批准后续跑）。有真 `twin_id`。`provenance=qccd-twin`。有 `counts`。不要 signoff。

抄到的句柄与摘要：

| 字段 | 值 |
|------|-----|
| twin_id | `5c9ce47cda91d673598ba1283fed4e5ab4c1c17d2c770245ecab2534e3e071a5` |
| provenance | `qccd-twin` |
| shots_actual | 8 |
| counts | `{"00": 4, "11": 4}` |

payload 原文：

```json
{
  "counts": {
    "00": 4,
    "11": 4
  },
  "provenance": "qccd-twin",
  "shots_actual": 8,
  "twin_id": "5c9ce47cda91d673598ba1283fed4e5ab4c1c17d2c770245ecab2534e3e071a5"
}
```

同一次再打的原始 `POST /v1/twin/run` `mode=pipeline` HTTP 200（counts 会抖；句柄仍是 TwinRun 发的同一 `twin_id`）：

```json
{"schema": "ionstack_twin_run", "schema_version": "2", "package_version": "10.0.0", "twin_id": "5c9ce47cda91d673598ba1283fed4e5ab4c1c17d2c770245ecab2534e3e071a5", "ok": null, "counts": {"00": 3, "11": 5}, "makespan_ns": 3040.0, "total_motion_ns": 2800.0, "motion_kind": "transport", "total_transport_ns": 2800.0, "report": null}
```

`http_code=200`

没有真 TwinRun `twin_id` 就失败。skip 当绿 = 没做完。

## 不算什么

- **identity 单独不算已通**。`GET /v1/twin/identity` 200、`invoke` identity `live=true`，都还没有 TwinRun。
- 这次是 **pipeline TwinRun 才算**。`invoke("ionstack_twin_run")` `mode=pipeline` 出真 `twin_id` + `qccd-twin` + `counts`。
- **不算 G0**。没在 3080 填模型，没走「扫氢分子」。
- **不算 G2**。没有客户面回执演示。
- **不算接线 Pennylane**。Pennylane 仍只 reserved。
- 不算 `mode=signoff` 已通。signoff 要 CAL；CAL 不进工具。
- 不算改了 [A-03_live.md](A-03_live.md) 的「未打 / 未证明」。
- 未改 `adapters/ionstack.py`。未 commit。

## 测

```bash
cd /Users/shl/nvidia/qagent
QAGENT_TWIN_URL=http://127.0.0.1:8765 PYTHONPATH=src python3 tests/test_a03g.py
PYTHONPATH=src python3 tests/test_a03c.py
PYTHONPATH=src python3 tests/run_tests.py
```

没有真 TwinRun `twin_id` 必须失败。skip 当绿 = 没做完。不 commit。
