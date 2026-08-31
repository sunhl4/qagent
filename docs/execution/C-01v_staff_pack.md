# C-01v · 未就绪展开组内模型栏

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P · C-01v |
| 范围 | `apps/customer-shell/app.js` · 本笔记 · `qagent/tests/test_c01v.py` |
| 未改 | `chat.py` · `agent.py` · `run_tests.py` · `PROGRESS.md` |
| 状态 | 未就绪打开设置时展开 `details.staff-pack`。客户角色不展开。**不算 G0**。未 commit。 |

## 产品锁

- 组内模型栏原先折叠。人只看见密钥或只填模型名，G0 填不上地址。
- 完成线：`revealStaffPackIfNeeded`。`!ready` 且不是 customer 才 `pack.open = true`。boot / 设置按钮 / `openSettingsDialog` 都走它。`test_c01e` 的 `showModal` 仍在 boot。
- 气泡仍 `send("批准")`。
- 本机曾被测污染的 `dsh.env` 死 `:9` 已清掉，只留 HOME。不从 env 把 ready 改 true。
- **不算 G0**。人还没填地址、模型名、钥匙。skip 当绿 = 没做完。未 commit。

## 不算什么

- **不算 G0**。ready 仍 false。没有代填密钥。
- 未假 `twin_id`。未接线 Pennylane。未 commit。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_c01v.py
PYTHONPATH=src python3 tests/test_c01e.py
PYTHONPATH=src python3 tests/test_c01u.py
PYTHONPATH=src python3 tests/run_tests.py
```

客户脸展开组内、或改气泡走 `/approve` 必须失败。skip 当绿 = 没做完。不 commit。
