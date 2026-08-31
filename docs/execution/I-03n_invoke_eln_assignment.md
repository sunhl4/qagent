# I-03n · invoke 写 ELN 带 assignment_id

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | A2 · I-03n |
| 范围 | `qagent/src/qagent/services/invoke.py` · `vibe_path.py` · `assignment.py` · 本笔记 · `qagent/tests/test_i03n.py` |
| 未改 | `chat.py` · `agent.py` · `run_tests.py` · `PROGRESS.md` · ionstack 核 |
| 状态 | 交办 `run` / `approve` 走的 invoke 把 `assignment_id` 写进 pin / 估计 / 签收 / B3 / claim_blocked。无 id 的调用仍不打标签。fork 才能拷到这些行。**不算 G0**。未 commit。 |

## 产品锁

- I-03a：ELN 五类事件。`invoke()` 原先写下估计/签收，但不带 `assignment_id`，`replay(交办)` 看不见，fork 拷不到。
- 完成线：`invoke(..., assignment_id=)`。`run_vibe_path` 和交办 run/approve/resume 传入交办 id。未批准跑出估计行。批准后有签收/B3 行。fork 复制后无 `twin_id`。
- 评测 / 裸 invoke 不传 id，事件仍可不挂交办。
- 不把 `assignment_id` 塞进工具 args。不发明第四个句柄。不铸 `twin_id`。
- **不算 G0 / G1**。没有填模型。skip 当绿 = 没做完。未 commit。

## 2026-08-27 真实脸

未批准 `asg_70aea5323481`：ELN 有 `recipe_pin` / `estimate`，无 `twin_id`。fork 后估计仍在。批准 `asg_1782987fc2cd`：ELN 有 `twin_signoff` / `b3`。fork 后无 `twin_id`。3080 HTTP `asg_ef4914594c7f` run 未批同样有 estimate。

## 不算什么

- **不算 G0**。ready 仍 false。
- 未把 CAL 塞进工具。未假 `twin_id`。未 commit。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_i03n.py
PYTHONPATH=src python3 tests/test_i03m.py
PYTHONPATH=src python3 tests/test_r03g.py
PYTHONPATH=src python3 tests/run_tests.py
```

交办 run 后 `replay(id)` 没有估计必须失败。skip 当绿 = 没做完。不 commit。
