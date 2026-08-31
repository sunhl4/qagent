# I-01p · 交办脸带上 `aer_provenance`

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P · I-01p |
| 范围 | `qagent/src/qagent/models/assignment.py` · 本笔记 · `qagent/tests/test_i01p.py` |
| 未改 | `vibe_path.py` · `shell_http.py` · `chat.py` · `agent.py` · `run_tests.py` · `PROGRESS.md` · ionstack 核 |
| 状态 | `face_payload()` 在 `columns.aer_provenance` ∈ {aer, ibm, cirq} 时带该字。永不把 `qccd-twin` 写成 aer。**不算 G0**。**不算 G1**。未 commit。 |

## 产品锁

- G1：「这是不是 Aer 签收的？」跑过 Aer 要看见 `provenance=aer`，且不是孪生签收。
- 完成线：已签收 GET 有 `aer_provenance=aer`。`qccd-twin` 不进该字段。
- 不回 `columns` / identity / counts。不是句柄。
- **不算 G0 / G1**。人还没按组内剧本走完。
- skip 当绿 = 没做完。未 commit。

## 2026-08-27 真实脸

`asg_b281b611c8f6` 已签收，`aer_provenance=aer`。孪生句柄仍在 `handles.twin_id`，不是 aer。

## 不算什么

- **不算 G0**。ready 仍 false。
- **不算 G1**。只把已有 Aer 来源露到脸上。
- 未改 `chat.py`。未 commit。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_i01p.py
PYTHONPATH=src python3 tests/run_tests.py
```

没有 `aer_provenance` 或把 `qccd-twin` 写进去必须失败。skip 当绿 = 没做完。不 commit。
