# C-01x · 本任务轨：短结论、不换已画线路

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-28 |
| 角色 | P · C-01x |
| 范围 | `customer-shell` · `customer_voice.py` · `chat.py` · `shell_http.py` · `assignment.face_payload` 时间戳 · `vibe-across-engines` · qiskit/qchem 工具说明 · 本笔记 · `tests/test_c01x.py` |
| 未改 | `assignment.py` 黄金路径 / pipeline 次数 · 科学核 · `agent.py` |
| 状态 | 右侧只画本任务一条在办/回执。HTTP 回复抹句柄和内部名。已画的线路不被后来的薄导出换掉。三轮独立审查已按结论改完。**不算 G0**。未 commit。 |

## 产品锁

- 侧栏标题是「本任务」。HTML 仍留「在办」。在办/回执/ELN 仍先取最近八条窗口，脸上只画当前一条。
- 欢迎页仍拼引擎 chips（测锁），CSS 藏起来。目录在设置里。
- 对人短结论。不要报工具名、配方名。JS 仍不许出现 `ionstack_twin_run`。
- 交办脸带 `created_at` / `updated_at`，本任务按时间取最新一条，不是「永远最后一条已签收」。
- 同一回合后到的薄导出不能盖掉更完整的钉住结果。轮询若先画了薄图，后来的更完整 `circuit_id` 可以换上。客户附上的线路可以换。HTTP 线路条带比特数和门数，仍无 `qasm3` / `body`。
- 气泡仍 `send("批准")`。
- **不算 G0 / G1 / G2**。skip 当绿 = 没做完。未 commit。

## 不算什么

- **不算 G0**。人还没按演示剧本走完。
- 未把 CAL / shuttle 塞进工具。未假 `twin_id`。未 commit。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_c01x.py
PYTHONPATH=src python3 tests/test_c01w.py
PYTHONPATH=src python3 tests/test_c01o.py
```

脸上再画出一墙旧回执、或用后到的 2 比特线换掉已画的 UCCSD，必须失败。skip 当绿 = 没做完。不 commit。
