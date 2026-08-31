# A-01i · 活 get_job

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | S1 · A-01i |
| 范围 | 只本笔记 + `qagent/tests/test_a01i.py` |
| 未改 | `qagent/src/**` · `test_a01h.py` · `A-01_live.md` · `run_tests.py` · `PROGRESS.md` · qdata 核 · workplace 密钥 |
| 状态 | `:8787` 通。先 `invoke("qdata_submit_job")` 有 `job_id`，再 `invoke("qdata_get_job")` 有 `status`，不是 `done`。无 `twin_id`。**不算 G0**。**不算 G2**。 |

## 产品锁

- 完成线是活 HTTP + `invoke("qdata_get_job")`，不是 raw CLI。
- `QAGENT_QDATA_URL` 有值时 `get_job` 走 `GET /v1/jobs/{job_id}`。`_public_job` 只留 `status` / `summary` / 可选 `asset_id`。
- 不铸 `twin_id`。只有 TwinRun 发 `twin_id`。句柄只有 `circuit_id` / `asset_id` / `twin_id`。`job_id` 是 HTTP 回执，不是第四句柄。
- 测里 `export QAGENT_QDATA_URL=http://127.0.0.1:8787`。可隔离 store。**不** `apply_env()`。**不**读本机 `workplace.json`。
- 旧 [A-01_live.md](A-01_live.md) 的「未打 / 未证明」合同不动。那条是 gated skip 探活，不是本包。
- **skip 当绿 = 没做完**。`:8787` 不通或 `get_job` 失败必须失败。
- **不编** accepted。**未写** job 已完成。本包抄到的 `payload.status` 是 `failed`，不是 `done`。
- **不算 G0 / G2**。Pennylane 仍 reserved。

## 2026-08-27 真实 get_job payload

测只 export `QAGENT_QDATA_URL=http://127.0.0.1:8787`，store 隔离在 `qagent/.qagent/test-a01i-store`。不 `apply_env()`。不读 `workplace.json`。

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
{"job_id":"712337a00c4741a8a245c52e7a7cc8cf","status":"queued"}
```

`GET /v1/jobs/{job_id}`（invoke 提交的那条）：

```http
GET http://127.0.0.1:8787/v1/jobs/8179cf73884f457ab50ac4e27c81536d
```

```json
{"job_id":"8179cf73884f457ab50ac4e27c81536d","kind":"surrogate","status":"failed","progress":"","result":{"error":"KeyError: 'train_features'"},"created":1787774640.569649,"updated":1787774640.570755}
```

调用：

```text
invoke("qdata_submit_job", "lab", {"kind": "surrogate", "payload": {}})
invoke("qdata_get_job", "lab", {"job_id": "<submit 的 job_id>"})
```

结果：submit `status=ok`，只要 `job_id`。get_job `status=ok`。payload 有 `status` 与 `summary`。`payload.status` 是 `failed`，不是 `done`。无 `twin_id`。无 `asset_id`（可有可无）。未编 accepted。

抄到的 invoke 回执：

| 字段 | 值 |
|------|-----|
| job_id | `8179cf73884f457ab50ac4e27c81536d` |
| kind | `surrogate` |
| invoke | `ok` |
| payload.status | `failed` |
| HTTP GET job_id | `712337a00c4741a8a245c52e7a7cc8cf` |

submit payload 原文：

```json
{
  "job_id": "8179cf73884f457ab50ac4e27c81536d"
}
```

get_job payload 原文（`_public_job` 之后）：

```json
{
  "status": "failed",
  "summary": {
    "error": "KeyError: 'train_features'"
  }
}
```

空 `surrogate` payload 在活 API 上立刻 `failed`（缺 `train_features`）。本包只证 `get_job` 通，不把 job 写成已完成。

## 不算什么

- **不算 G0**。没在 3080 填模型，没走「扫氢分子」。
- **不算 G2**。没有客户面回执演示。
- 不算接线 Pennylane。Pennylane 仍只 reserved。
- 不算改了 [A-01_live.md](A-01_live.md) 的「未打 / 未证明」。
- 不算把 job 写成已完成。抄到的是 `failed`，不是 `done`。
- **未 commit**。

## 测

```bash
cd /Users/shl/nvidia/qagent
QAGENT_QDATA_URL=http://127.0.0.1:8787 PYTHONPATH=src python3 tests/test_a01i.py
PYTHONPATH=src python3 tests/run_tests.py
```

`:8787` 不通或 `get_job` 失败必须失败。skip 当绿 = 没做完。不 commit。
