# I-01q · 回执脸带上 `shots_actual`

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P · I-01q |
| 范围 | `qagent/src/qagent/models/assignment.py` · `services/assignment.py` · `apps/customer-shell/app.js` · `app.css` · 本笔记 · `qagent/tests/test_i01q.py` |
| 未改 | `chat.py` · `agent.py` · `run_tests.py` · `PROGRESS.md` · 封条 `receipt_payload` |
| 状态 | `face_payload()` 在 `columns.shots_actual` 为正整数时带该数。回执画「实打 · N 发」。封条不写 `shots_actual`。**不算 G0/G1**。未 commit。 |

## 产品锁

- G2 下载的是回执，不是 ELN。ELN 已能画实打，回执/在办原先没有 `shots_actual`。
- 完成线：`face_shots_actual` 只认正整数。只从带 `twin_id` 的 Twin payload 抄进 `columns`。只有 `signed` 的 `face_payload()` 带 `shots_actual`。`paintFaceRow` 读 `row.shots_actual`，class `receipt-shots`。不读 `columns`。Aer 步骤的发数不是实打。回执栏仍取最早 8 条已签收（C-01m 锁）。
- 封条 JSON 不加 `shots_actual`，以免改核验哈希。
- 气泡仍 `send("批准")`。
- **不算 G0 / G1**。没有填模型。skip 当绿 = 没做完。未 commit。

## 2026-08-27 真实脸

隔离 `create → run → approve` 后 `face_payload().shots_actual=8`。3080 HTTP `asg_8ea0d70e17f9` 同样。旧签收若 `columns` 里没有实打，不编造。

## 不算什么

- **不算 G0**。ready 仍 false。
- **不算 G1 / G2**。只把已有实打发数露到脸上。
- 未假 `twin_id`。未接线 Pennylane。未 commit。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_i01q.py
PYTHONPATH=src python3 tests/test_i01o.py
PYTHONPATH=src python3 tests/test_c01o.py
PYTHONPATH=src python3 tests/test_c01j.py
PYTHONPATH=src python3 tests/test_r03g.py
PYTHONPATH=src python3 tests/run_tests.py
```

没有 `shots_actual`、画 ELN class、或改气泡走 `/approve` 必须失败。skip 当绿 = 没做完。不 commit。
