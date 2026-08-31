# I-03l · ELN HTTP 只回最新 20 行

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P · I-03l |
| 范围 | `qagent/src/qagent/entrypoints/shell_http.py` · 本笔记 · `qagent/tests/test_i03l.py` |
| 未改 | `models/eln.py` 的 `short_payload()` · `services/eln.py` · `chat.py` · `agent.py` · `run_tests.py` · `PROGRESS.md` |
| 状态 | `GET /api/eln` 租户过滤后再取尾 20 行。盘上仍全文。不改 `short_payload()`。**不算 G0**。**不算 G2**。未 commit。 |

## 产品锁

- 活盘 `eln.jsonl` 已 8000+ 行。脸一次 GET 全量，实验记录空窗。
- 完成线：HTTP 脸最多 20 条，保留最新。`read_eln()` 不截断。
- 仍 `short_payload(drop_twin(row))`。不改 short_payload()。无 POST。无 `twin_id`。
- **不算 G0 / G2**。
- skip 当绿 = 没做完。未 commit。

## 2026-08-27 真实脸

隔离夹具 25 条估计 + 1 条旧钉住：HTTP 20 条，旧钉住不在脸。活 3080 `GET /api/eln` ≤20。

## 不算什么

- **不算 G0**。ready 仍 false。
- **不算 G2**。只让组内 ELN 画得出来。
- 未改 short_payload()。未 commit。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_i03l.py
PYTHONPATH=src python3 tests/test_i03d.py
PYTHONPATH=src python3 tests/run_tests.py
```

脸仍回 8000 行必须失败。skip 当绿 = 没做完。不 commit。
