# I-03q · ELN 脸压重复交办行

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P · I-03q |
| 范围 | `qagent/src/qagent/services/eln.py` · `entrypoints/shell_http.py` · 本笔记 · `qagent/tests/test_i03q.py` |
| 未改 | `short_payload()` · `chat.py` · `agent.py` · `run_tests.py` · `PROGRESS.md` |
| 状态 | 无过滤的 `GET /api/eln` 每个交办只留最新一条 assignment。盘上仍全文。帽仍 20。**不算 G0/G1**。未 commit。 |

## 产品锁

- `_persist` 每次改状态都写 assignment。总跑后最近 20 条被交办状态冲掉，签收 / B3 / 实打从脸和活测里消失。
- 完成线：`collapse_assignment_events`。无 `assignment_id` 的 GET 先压再取尾 20。带 `assignment_id` 的 GET 不压。`read_eln()` 不截断。
- 不改 cap 20。不复活旧 recipe_pin（I-03l）。不画 `twin_id`。
- **不算 G0 / G1**。skip 当绿 = 没做完。未 commit。

## 不算什么

- **不算 G0**。ready 仍 false。
- 未假 `twin_id`。未 commit。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_i03q.py
PYTHONPATH=src python3 tests/test_i03l.py
PYTHONPATH=src python3 tests/test_i03p.py
PYTHONPATH=src python3 tests/run_tests.py
```

脸仍回每个交办的全部状态行必须失败。skip 当绿 = 没做完。不 commit。
