# C-01u · 设置保存诚实

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P · C-01u |
| 范围 | `apps/customer-shell/app.js` · `index.html` · 本笔记 · `qagent/tests/test_c01u.py` |
| 未改 | `chat.py` · `agent.py` · `workplace.py` · `run_tests.py` · `PROGRESS.md` |
| 状态 | 无 token 的 PUT 不再假装已保存。只填模型名会提示还要接口地址。**不算 G0**。未 commit。 |

## 产品锁

- 人只填模型名、或没带 `?token=` 打开 3080 时，保存写不进盘，脸上却说「设置已保存」。G0 卡在这里。
- 完成线：`saveSettings` 认 `!res.ok`。403 说「保存要组内 token」。缺地址说「还要填接口地址，例如 https://api.deepseek.com/v1」。组内模型栏写明钥匙在「密钥 → API Key」。
- 气泡仍 `send("批准")`。
- **不算 G0**。人还没把地址、模型名、钥匙存上。skip 当绿 = 没做完。未 commit。

## 不算什么

- **不算 G0**。ready 仍 false。没有代填密钥。
- 未假 `twin_id`。未接线 Pennylane。未 commit。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_c01u.py
PYTHONPATH=src python3 tests/test_c01d.py
PYTHONPATH=src python3 tests/test_i01m.py
PYTHONPATH=src python3 tests/run_tests.py
```

403 仍说已保存、或改气泡走 `/approve` 必须失败。skip 当绿 = 没做完。不 commit。
