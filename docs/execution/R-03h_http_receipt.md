# R-03h · 3080 HTTP 批准签收回执

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | S2 · R-03h |
| 范围 | 只本笔记 + `qagent/tests/test_r03h.py` |
| 未改 | `assignment.py` · `vibe_path.py` · `shell_http.py` · `chat.py` · `agent.py` · `run_tests.py` · `PROGRESS.md` · ionstack 核 · workplace 密钥 · CAL / shuttle |
| 状态 | 3080 脸重载新代码后，`POST /api/assignments` → `run` → `approve`（带 token）回 `status=signed`。`GET …/receipt` `signed=true`，有 TwinRun `twin_id` + sources 含 `qccd-twin`。`POST /api/receipts/verify` `ok=true`。无 token 批准仍 403。**CAL 不进工具**。**不算 G0**。**不算 G2**。未 commit。 |

## 产品锁

- 完成线是活 3080 HTTP：人批之后回执 `signed=true`，当且仅当有 TwinRun `twin_id` 且 sources 含 `qccd-twin`。
- 无 token 的 `POST …/approve` 仍是 `{"error": "approval requires QAGENT_SHELL_TOKEN"}`。
- 旧脸进程若仍是 `ask.args.mode=signoff`，活 Twin 400：`signoff mode requires calibration`。本包不改源码；调度已只杀 `shell_cli --serve` 再 `start_ui.sh` 加载 A-03i / R-03g 的 pipeline。不 `pkill dsh`。
- **只有** ionstack TwinRun 能发 `twin_id`。不铸本地 `twin_id`。
- **不算 G0 / G2**。没在 3080 填模型，没让客户点「批准上机」走完整演示。
- skip 当绿 = 没做完。死 Twin / 无 token 必须诚实失败。不编 `accepted:true`。未 commit。

## 2026-08-27 活 HTTP

token 只用于请求头，不是密钥。调度已起 `:8765` 与 3080。

### 1. 无 token 批准仍 403

```json
{"error": "approval requires QAGENT_SHELL_TOKEN"}
```

### 2. 带 token · create → run → approve → receipt

| 字段 | 值 |
|------|-----|
| assignment_id | `asg_b281b611c8f6` |
| twin_id | `5c9ce47cda91d673598ba1283fed4e5ab4c1c17d2c770245ecab2534e3e071a5` |
| sources | 含 `qdata-cli` / `aer` / `qccd-twin` |
| signed | true |
| verify | ok |

没有真 TwinRun `twin_id` 就失败。skip 当绿 = 没做完。

## 不算什么

- **不算 G0**。workplace `ready` 仍 false。
- **不算 G2**。这是 HTTP 交办批准，不是客户脸点批准上机走完剧本。
- 不算 `mode=signoff` 已通。signoff 要 CAL；CAL 不进工具。
- 未改服务层（R-03g 已改 pipeline）。未 commit。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_r03h.py
PYTHONPATH=src python3 tests/run_tests.py
```

没有真 TwinRun `twin_id` 必须失败。skip 当绿 = 没做完。不 commit。
