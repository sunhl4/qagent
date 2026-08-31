# C-01w · 商业脸：排版、线路进出、不念随机码

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-28 |
| 角色 | P · C-01w |
| 范围 | `customer-shell` · `pin.py` · `circuit_text.py` · `shell_http.py` · `chat.py` · `dsh_session.py` · `vibe-across-engines` · 本笔记 · `tests/test_c01w.py` |
| 未改 | `assignment.py` 黄金路径 · 科学核 · `agent.py` |
| 状态 | 对话按 Markdown 排版。`GET /api/circuits/<id>/program` 给人/脚本下载 OpenQASM，不进模型上下文。`POST /api/circuits` 收下客户 QASM。脸上不出现 `circ_` / `asset_` / `twin_` / session 随机码。**不算 G0**。未 commit。 |

## 产品锁

- 客户不关心句柄哈希。在办/回执/ELN/图注只写「这份线路」「已备好的数据」「已在我们的机器上签收」。
- 图、估计、回执走固定模块。回复做标题/列表/表格，并抹掉模型万一念出的句柄。
- 下载走 HTTP `.../program`。`GET /api/circuits/<id>` 仍无 `qasm3` / `body` / `twin_id`。不要 `qiskit_export` 抽全文进对话。
- 上传只 pin，不把 QASM 塞进 `/api/chat`。下一句若已有线路，只把 `circuit_id` 交给运行时，并嘱咐不要念出来。
- 气泡仍 `send("批准")`。JS 仍不许出现 `ionstack_twin_run`。
- 超时还没新回合时，`wait_for_turn` 不把上一轮回复/电路图贴到这一轮。
- **不算 G0 / G1 / G2**。skip 当绿 = 没做完。未 commit。

## 不算什么

- **不算 G0**。人还没按演示剧本走完。
- 未把 CAL / shuttle 塞进工具。未假 `twin_id`。未 commit。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_c01w.py
PYTHONPATH=src python3 tests/test_c01q.py
PYTHONPATH=src python3 tests/test_h01l.py
```

脸上再画出 `circ_` / `asset_` 随机码必须失败。skip 当绿 = 没做完。不 commit。
