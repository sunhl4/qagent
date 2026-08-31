# C-01q · 在办/回执画 circuit_id 与 asset_id

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P · C-01q |
| 范围 | `qagent/apps/customer-shell/app.js` · `app.css` · 本笔记 · `qagent/tests/test_c01q.py` |
| 未改 | `assignment.py` · `shell_http.py` · `chat.py` · `agent.py` · `run_tests.py` · `PROGRESS.md` |
| 状态 | 在办/回执只读 `handles.circuit_id` / `handles.asset_id`，画「这份线路」「已备好的数据」，不把随机句柄念给客户。不读 `columns`。气泡仍 `send("批准")`。**不算 G0/G1**。未 commit。 |

## 产品锁

- G1「扫 H₂，先估计」要先 pin，对话/在办里出现 `circuit_id`。句柄早已在 `face_payload().handles`，脸没画。
- 完成线：`faceCircuitId` / `faceAssetId` 只读 handles。在办 `inbox-circuit` / `inbox-asset` 画「这份线路」「已备好的数据」。回执 `receipt-circuit` / `receipt-asset`。脸上不出现 `circ_` / `asset_` 随机码。
- 不读 `columns` / `ask.args` / `brief` / `recipe`。不发明第四个句柄。`twin_id` 仍只在已签收画。
- 气泡仍 `send("批准")`。在办按钮仍 HTTP `assignmentAction`。
- **不算 G0 / G1**。没有填模型。人还没走完 G1 四步。skip 当绿 = 没做完。未 commit。

## 2026-08-27 真实脸

活 HTTP 交办脸已带 `handles.circuit_id`。3080 在办/回执读句柄，脸上只写「这份线路」「已备好的数据」。句柄留在 API / 下载文件，不进可见文案。空提示已藏。

## 不算什么

- **不算 G0**。ready 仍 false。
- **不算 G1**。对话路径仍要人填模型。
- 未把 CAL 塞进工具。未假 `twin_id`。未 commit。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_c01q.py
PYTHONPATH=src python3 tests/test_c01j.py
PYTHONPATH=src python3 tests/run_tests.py
```

在办/回执读 `columns` 或 `ask.args` 必须失败。skip 当绿 = 没做完。不 commit。
