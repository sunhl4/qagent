# I-01n · 交办脸带上估计 `makespan_ns`

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P · I-01n |
| 范围 | `qagent/src/qagent/models/assignment.py` · 本笔记 · `qagent/tests/test_i01n.py` |
| 未改 | `vibe_path.py` · `shell_http.py` · `chat.py` · `agent.py` · `run_tests.py` · `PROGRESS.md` · ionstack 核 |
| 状态 | `face_payload()` 在 `columns.makespan_ns` 有值时带整数估计。不回 `columns` / identity / counts。无 `twin_id`。**不算 G0**。**不算 G1**。未 commit。 |

## 产品锁

- G1：「扫 H₂，先估计」要看见 `makespan_ns`，Twin 未批。HTTP 交办脸原先只回句柄，估计闷在 `columns` 里。
- 完成线：`run()` 之后 `face_payload()` / `GET /api/assignments/{id}` 有 `makespan_ns`。整千用 int。不是句柄。
- 仍不回 `columns` / `identity` / circuit body。未批准没有 `twin_id`。
- **不算 G0 / G1**。没在 3080 填模型走「扫氢分子」。
- skip 当绿 = 没做完。未 commit。

## 2026-08-27 真实脸

服务层 `create`→`run`：`status=needs_ask`，`makespan_ns=4800`。无 `twin_id`。

3080 HTTP `POST /run`：`asg_08372d9b8409`，`makespan_ns=3040`，`status=needs_ask`。无 `twin_id`。无 `columns`。

## 不算什么

- **不算 G0**。ready 仍 false。
- **不算 G1**。只把已有估计露到脸上，人还没按组内剧本走完。
- 未改 `chat.py`。未 commit。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_i01n.py
PYTHONPATH=src python3 tests/run_tests.py
```

没有 `makespan_ns` 必须失败。skip 当绿 = 没做完。不 commit。
