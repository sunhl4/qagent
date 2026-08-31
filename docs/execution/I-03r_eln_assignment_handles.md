# I-03r · 交办 ELN 写下线路/资产

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P · I-03r |
| 范围 | `qagent/src/qagent/services/eln.py` · `assignment.py` · `apps/customer-shell/app.js` · `app.css` · 本笔记 · `qagent/tests/test_i03r.py` |
| 未改 | `chat.py` · `agent.py` · `run_tests.py` · `PROGRESS.md` |
| 状态 | `_persist` 把 `circuit_id` / `asset_id` 写入 assignment 事件。不写 `twin_id`。脸画「这份线路」「已备好的数据」，不念随机句柄。**不算 G0/G1**。未 commit。 |

## 产品锁

- 交办 ELN 原先只有 status / room。在办已能看见线路/资产，实验记录看不见。
- 完成线：`append_assignment(..., circuit_id=, asset_id=)`。`sanitize_handles` 后只取这两项。`elnCircuitId` / `elnAssetId`。`eln-circuit` / `eln-asset`。不画 `twin_id`。不读 `columns`。
- 气泡仍 `send("批准")`。
- **不算 G0 / G1**。没有填模型。skip 当绿 = 没做完。未 commit。

## 不算什么

- **不算 G0**。ready 仍 false。
- 未假 `twin_id`。未 commit。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_i03r.py
PYTHONPATH=src python3 tests/test_i03g.py
PYTHONPATH=src python3 tests/test_i03q.py
PYTHONPATH=src python3 tests/run_tests.py
```

assignment 事件带 `twin_id` 必须失败。skip 当绿 = 没做完。不 commit。
