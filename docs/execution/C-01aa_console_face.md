# C-01aa · 连线硬化 + 离子阱控制台脸

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-29 |
| 角色 | P · C-01aa |
| 范围 | `customer-shell` 视觉 · `send` / `pollStatus` · `chat.py` 在办文案 · HTTP 不甩 HTML 500 · 本笔记 · `tests/test_c01aa.py` |
| 未改 | `assignment.py` 黄金路径 · 科学核 · `agent.py` · Overleaf |
| 状态 | 「没连上」不再吞掉还在办的一轮。脸改成控制台式样。**不算 G0**。未 commit。 |

## 错在哪

- `/api/chat` 两秒就回 `running`。真回复在 `/api/chat/status`。
- 脸把 `json()` / 渲染 / 轮询的任何抛错都说成「这次没连上」。
- 轮询一次失败就停。人连发两句都看不见公式。

## 产品锁

- 气泡仍 `send("批准")`。JS 仍不许出现 `ionstack_twin_run`。
- 欢迎仍是「你想做什么？」。chips 仍拼 `pack.label · pack.kind · pack.status`。
- HTML 仍有「在办」「实验记录 / ELN」「不必报内部配方名」「附上线路」。
- CSS 仍有 `--radius` / `--shadow` / `--gold-dim`，侧栏 `grid-row: 2 / 4`。
- 在办占位不再提 dsh session。
- **不算 G0 / G1 / G2**。skip 当绿 = 没做完。未 commit。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_c01aa.py
PYTHONPATH=src python3 tests/test_c01y.py
PYTHONPATH=src python3 tests/test_c01z.py
PYTHONPATH=src python3 tests/test_c01x.py
```

轮询一次失败就 `return`，或在办文案再写 dsh session，必须失败。skip 当绿 = 没做完。不 commit。
