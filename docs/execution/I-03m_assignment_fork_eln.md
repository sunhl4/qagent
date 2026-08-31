# I-03m · 交办 fork 复制 ELN，不带走 twin_id

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | A2 · I-03m |
| 范围 | `qagent/src/qagent/services/eln.py` · `assignment.py` · 本笔记 · `qagent/tests/test_i03m.py` |
| 未改 | `chat.py` · `agent.py` · `run_tests.py` · `PROGRESS.md` · ionstack 核 |
| 状态 | `assignment.fork()` 先建未签收交办，再 `copy_events_for_fork`。复制行 `drop_twin`。记下 `parent_assignment_id`。**不算 G0**。未 commit。 |

## 产品锁

- I-03b：fork/replay，科学真源仍 qdata。ELN `fork()` 会复制事件并丢 `twin_id`。交办 HTTP `fork` 原先只 `create()`，replay 是空的。
- 完成线：交办 fork 后新 id 的 `replay()` 有估计/B3 等拷贝，无 `twin_id`，有 `parent_assignment_id`。新交办 `status=draft`，handles 无 `twin_id`。
- 脸不回 `error` 原文、不回 `columns`。不发明第四个句柄。
- **不算 G0 / G1**。没有填模型。skip 当绿 = 没做完。未 commit。

## 2026-08-27 真实脸

隔离夹具：fork 后 ELN 有估计拷贝、无 `twin_id`、有 parent。活 HTTP `asg_b281b611c8f6` → `asg_2c75aa13001c` `draft`，handles 无 `twin_id`，ELN 记 parent。源交办盘上当时只有 assignment 事件，拷贝跳过这类。

## 不算什么

- **不算 G0**。ready 仍 false。
- 未把 CAL 塞进工具。未假 `twin_id`。未 commit。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_i03m.py
PYTHONPATH=src python3 tests/test_i03.py
PYTHONPATH=src python3 tests/run_tests.py
```

fork 后 ELN 仍带 `twin_id` 必须失败。skip 当绿 = 没做完。不 commit。
