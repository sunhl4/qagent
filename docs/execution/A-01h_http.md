# A-01h · 活 qdata HTTP

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | S1 · A-01h |
| 范围 | 只本笔记 + `qagent/tests/test_a01h.py` |
| 未改 | `qagent/src/**` · `test_a01.py` · `test_a01g.py` · `A-01_live.md` · `run_tests.py` · `PROGRESS.md` · qdata 核 · workplace 密钥 |
| 状态 | `:8787` 通。`invoke("qdata_submit_job")` 有 `job_id`。无 `twin_id`。**不算 G0**。**不算 G2**。**不算接线 Pennylane**。 |

## 产品锁

- 完成线是活 HTTP + `invoke`，不是 raw CLI `qdata run`。
- `QAGENT_QDATA_URL` 有值时 `submit_job` 走 `POST /v1/jobs/{kind}`，只要 `job_id`。kind 允许 `sample-to-solver` / `shadow-predict` / `surrogate`。
- 不铸 `twin_id`。只有 TwinRun 发 `twin_id`。句柄只有 `circuit_id` / `asset_id` / `twin_id`。`job_id` 是 HTTP 回执，不是第四句柄。
- 测里 `export QAGENT_QDATA_URL=http://127.0.0.1:8787`。可隔离 store。**不** `apply_env()`。**不**读本机 `workplace.json`。
- 旧 [A-01_live.md](A-01_live.md) 的「未打 / 未证明」合同不动。那条是 gated skip 探活，不是本包。
- **skip 当绿 = 没做完**。`:8787` 不通或没有 `job_id` 必须失败。
- **不编** accepted。**未写** job 已完成。HTTP 提交回的是 `queued`。
- **不算 G0 / G2**。**不算接线 Pennylane**。Pennylane 仍 reserved。

## 2026-08-27 真实 HTTP / invoke

调度已 `QAGENT_QDATA_HOME=/Users/shl/nvidia/qdata` 后跑 `bash scripts/start_qdata.sh`。Uvicorn 在 `http://127.0.0.1:8787`。测只 export `QAGENT_QDATA_URL`，store 隔离在 `qagent/.qagent/test-a01h-store`。不 `apply_env()`。不读 `workplace.json`。

`GET /v1/healthz`：

```http
GET http://127.0.0.1:8787/v1/healthz
```

```json
{"status":"ok","version":"1.0.0"}
```

`POST /v1/jobs/surrogate`（空 payload，活 API 接受）：

```http
POST http://127.0.0.1:8787/v1/jobs/surrogate
Content-Type: application/json

{}
```

```json
{"job_id":"02ff89a045c3485b98170576689daf24","status":"queued"}
```

调用：

```text
invoke("qdata_submit_job", "lab", {"kind": "surrogate", "payload": {}})
```

结果：invoke `status=ok`。payload 只有 `job_id`。无 `twin_id`。未写 job 已完成。未编 accepted。

抄到的 invoke 回执：

| 字段 | 值 |
|------|-----|
| job_id | `4ba3afa7fc97441ca8139e6a849da378` |
| kind | `surrogate` |
| HTTP POST job_id | `02ff89a045c3485b98170576689daf24` |
| HTTP status | `queued` |

payload 原文：

```json
{
  "job_id": "4ba3afa7fc97441ca8139e6a849da378"
}
```

## 不算什么

- **不算 G0**。没在 3080 填模型，没走「扫氢分子」。
- **不算 G2**。没有客户面回执演示。
- **不算接线 Pennylane**。Pennylane 仍只 reserved。
- 不算改了 [A-01_live.md](A-01_live.md) 的「未打 / 未证明」。
- 不算把 job 写成已完成。提交瞬间是 `queued`。
- **未 commit**。

## 测

```bash
cd /Users/shl/nvidia/qagent
QAGENT_QDATA_URL=http://127.0.0.1:8787 PYTHONPATH=src python3 tests/test_a01h.py
PYTHONPATH=src python3 tests/run_tests.py
```

`:8787` 不通或没有 `job_id` 必须失败。skip 当绿 = 没做完。不 commit。
