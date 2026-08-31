# C-01r · 已签收回执「再走一遍」

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P · C-01r |
| 范围 | `qagent/apps/customer-shell/app.js` · 本笔记 · `qagent/tests/test_c01r.py` |
| 未改 | `assignment.py` 脸字段 · `chat.py` · `agent.py` · `run_tests.py` · `PROGRESS.md` |
| 状态 | 已签收回执按钮 `assignmentAction(..., "fork")`。气泡仍 `send("批准")`。文案「不会带走 twin_id」。**不算 G0/G1**。未 commit。 |

## 产品锁

- I-03b 工作台要能 fork。HTTP `POST …/fork` 已在。脸原先只有下载/核验。
- 完成线：仅 `signed` 行有「再走一遍」。走 `/${verb}`，源码无 `"/approve"`。新交办未签收，不画绿封条。
- 气泡仍 `send("批准")`。在办批准仍 HTTP。
- **不算 G0 / G1**。没有填模型。skip 当绿 = 没做完。未 commit。

## 2026-08-27 真实脸

3080 `b611c8f6` 已签收回执行有「再走一遍」。点后对话出现「已分出未签收交办。不会带走 twin_id。」气泡仍 `send("批准")`。

## 不算什么

- **不算 G0**。ready 仍 false。
- **不算 G1**。对话路径仍要人填模型。
- 未假 `twin_id`。未 commit。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_c01r.py
PYTHONPATH=src python3 tests/test_c01m.py
PYTHONPATH=src python3 tests/test_c01j.py
PYTHONPATH=src python3 tests/run_tests.py
```

回执用 `send("批准")` 做 fork 必须失败。skip 当绿 = 没做完。不 commit。
