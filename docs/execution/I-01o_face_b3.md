# I-01o · 交办脸带上 `b3_verdict`

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P · I-01o |
| 范围 | `qagent/src/qagent/models/assignment.py` · 本笔记 · `qagent/tests/test_i01o.py` |
| 未改 | `vibe_path.py` · `shell_http.py` · `chat.py` · `agent.py` · `run_tests.py` · `PROGRESS.md` · ionstack 核 |
| 状态 | `face_payload()` 在 `columns.b3.verdict` 属于三枚举时带 `b3_verdict`。不回 `columns` / `b3` 对象 / identity。**不算 G0**。**不算 G1**。未 commit。 |

## 产品锁

- G1 批准后要看见 B3 字段。回执盘上已有 `columns.b3.verdict`，脸原先不带。
- 完成线：已签收 `GET /api/assignments/{id}` 有 `b3_verdict` ∈ {quantum_wins, classical_wins, inconclusive}。
- 不回 `qem_contract_ok` / `columns` / counts。不是句柄。
- **不算 G0 / G1**。人还没按组内剧本走完。
- skip 当绿 = 没做完。未 commit。

## 2026-08-27 真实脸

`asg_b281b611c8f6` 已签收，`b3_verdict=inconclusive`。无 `columns`。

## 不算什么

- **不算 G0**。ready 仍 false。
- **不算 G1**。只把已有 B3 露到脸上。
- 未改 `chat.py`。未 commit。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_i01o.py
PYTHONPATH=src python3 tests/run_tests.py
```

没有 `b3_verdict` 必须失败。skip 当绿 = 没做完。不 commit。
