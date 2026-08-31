# C-01y · 商业脸：仪器风布局与入口

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-28 |
| 角色 | P · C-01y |
| 范围 | `customer-shell` 视觉与入口 · `customer_voice` / Skill 短结论 · 本笔记 · `tests/test_c01y.py` |
| 未改 | `assignment.py` 黄金路径 · 科学核 · `agent.py` |
| 状态 | 主栏与侧栏分开。欢迎页给入口，不写死 UCCSD。新对话有 token 才 reset；无 token 只清这一页，不甩英文 403。**不算 G0**。未 commit。 |

## 产品锁

- 色板仍是金 / 离子蓝。CSS 用 `--radius` / `--shadow` / `--gold-dim`。
- 欢迎仍是「你想做什么？」。chips 仍拼 `pack.label · pack.kind · pack.status`，CSS 藏起来。
- 入口只有「先看看接了哪些软件」「先估计，先不上机」。没有氢分子 / UCCSD 写死。
- HTML 仍有「在办」「实验记录 / ELN」「不必报内部配方名」「附上线路」。
- 气泡仍 `send("批准")`。JS 仍不许出现 `ionstack_twin_run`。
- **不算 G0 / G1 / G2**。skip 当绿 = 没做完。未 commit。

## 不算什么

- **不算 G0**。人还没按演示剧本走完。
- 未把 CAL / shuttle 塞进工具。未假 `twin_id`。未 commit。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_c01y.py
PYTHONPATH=src python3 tests/test_c01.py
PYTHONPATH=src python3 tests/test_h01m.py
```

欢迎页再写死 UCCSD，或主栏被侧栏压住注入区，必须失败。skip 当绿 = 没做完。不 commit。
