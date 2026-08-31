# C-01p · 回执画 Aer 不是孪生签收

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P · C-01p |
| 范围 | `qagent/apps/customer-shell/app.js` · 本笔记 · `qagent/tests/test_c01p.py` |
| 未改 | `chat.py` · `assignment.py` · `shell_http.py` · `agent.py` · `run_tests.py` · `PROGRESS.md` |
| 状态 | 回执读 `row.aer_provenance` 画「Aer · 不是孪生签收」。不读 `columns`。气泡仍 `send("批准")`。**不算 G0**。**不算 G1**。未 commit。 |

## 产品锁

- G1 第 4 步：跑过 Aer 时脸要说明这不是孪生签收。
- 完成线：`faceAerProvenance(row)` 读脸字段。`aer` → 「Aer · 不是孪生签收」。IBM / Cirq 同样句式。有值才画 `.receipt-aer`。
- 不读 `row.columns`。不把 `qccd-twin` 画成 Aer。气泡仍 `send("批准")`。
- **不算 G0 / G1**。
- skip 当绿 = 没做完。未 commit。不伪造 `twin_id`。不编 `accepted:true`。

## 2026-08-27 真实脸

已签收短号 `b611c8f6` 画「Aer · 不是孪生签收」，同时仍画真 `twin_id` 与「B3 · 尚无定论」。

## 不算什么

- **不算 G0**。ready 仍 false。
- **不算 G1**。只画已有 Aer 来源。
- 未改 `chat.py`。未 commit。`send("批准")` 气泡不动。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_c01p.py
PYTHONPATH=src python3 tests/test_c01j.py
PYTHONPATH=src python3 tests/test_c01o.py
PYTHONPATH=src python3 tests/run_tests.py
```

回执仍不画 Aer 必须失败。skip 当绿 = 没做完。不 commit。
