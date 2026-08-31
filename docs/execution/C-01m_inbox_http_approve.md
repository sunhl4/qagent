# C-01m · 在办「批准上机」走 HTTP 交办

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P · C-01m |
| 范围 | `qagent/apps/customer-shell/app.js` · 本笔记 · `qagent/tests/test_c01m.py` |
| 未改 | `chat.py` · `assignment.py` · `shell_http.py` · `agent.py` · `run_tests.py` · `PROGRESS.md` · ionstack 核 · workplace 密钥 |
| 状态 | 在办「批准上机」走 `assignmentAction` → `POST /api/assignments/{id}/` + `approve`。先不上机走 `cancel`。对话气泡里的「批准上机」仍 `send("批准")`（mux 有 `rpcId` 才续跑）。源码不出现字面 `/approve`，保持 I-01c / C-01k 锁。**不算 G0**。**不算 G2**。未 commit。 |

## 产品锁

- G2 剧本：右侧在办点「批准上机」。R-03h 已证明 HTTP `approve` 能签出真 `twin_id`。对话 `send("批准")` 要 mux `rpcId`，空 mux 不能编 `accepted:true`。
- 完成线：在办按钮不再 `send("批准")`。带 token 的脸打交办 HTTP。无 token 仍 403，不铸 `twin_id`。
- 对话里 dsh 弹出的待批仍走 `send("批准")`，不另开第三套 loop。
- **不算 G0 / G2**。没在 3080 填模型走「扫氢分子」，没把客户演示标绿。
- skip 当绿 = 没做完。不编 `accepted:true`。未 commit。不伪造上机句柄。

## 改了什么

`assignmentAction(assignmentId, action)`：`POST /api/assignments/{id}/{action}`，headers 仍带 `X-QAGENT-APPROVE-TOKEN`。在办 yes=`approve`，no=`cancel`。聊天气泡不动。回执列表先画 `signed`，避免旧失败行把刚签收的挤出前 8 条。

浏览器点在办「批准上机」（`asg_eacd4fa9dfb8`）：气泡「已签收。右侧可下载短回执。」HTTP 回执 `signed=true`，`twin_id=5c9ce47cda91d673598ba1283fed4e5ab4c1c17d2c770245ecab2534e3e071a5`。

## 不算什么

- **不算 G0**。ready 仍 false。
- **不算 G2**。只把在办按钮接到已通的 HTTP 签收。人还没按客户剧本走完。
- 不算活 mux `accepted:true`。空 mux 仍不编。
- 未改 `chat.py`。未 commit。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_c01m.py
PYTHONPATH=src python3 tests/run_tests.py
```

在办仍 `send("批准")` 必须失败。skip 当绿 = 没做完。不 commit。
