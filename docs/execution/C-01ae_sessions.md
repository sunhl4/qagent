# C-01ae 对话列表（记账，不是房间）

日期：2026-08-29。状态：已落地，未 commit。不算 G0/G1/G2 通过，只是脸的最后一波。

## 探查结论（ae.1，先探查再开刀）

- `session.history` 给原始事件流，但 `fold_history` 每逢 `turn/start` 就清空 `texts`，且从不抽 user 消息——所以 `worker.snapshot` 只带**最后一轮**的 assistant 文本，不带全文。
- session 存根是每租户一个 `sessionId`（staff 文件 `{sessionId}`，租户边车 `by_tenant`），没有列表、标题、时间。
- 结论：snapshot 给不了回看全文。按计划只列「未结 + 新对话」，**不假装回看**。真回看得另起一波：新 fold 抽 user 消息、按轮配对、加切换写路径——那波会动到 c01x 锁住的 fold 行为，单列。

## 落地

- `dsh_session_store.py`：新边车 `dsh-session.journal.json`（`by_tenant` 桶，每条 `{session_id, title, created_at, updated_at, archived}`，每租户留 16 条）。staff 文件形状不变，仍是 `{sessionId}`。`journal_session` 只登记/触碰，标题只写一次；`archive_session_id` 把条目标成已清；`list_journal` 只读。
- `chat.py`：`turn()` 在建/续 session 后登记日志，标题取用户第一句的前 24 字（OSError 不拖垮对话）；`reset_chat()` 先归档再清指针；新 `list_sessions()` 出脸用行（标题、时间、当前/已清，最多 8 条，**不带 session_id**）。
- `shell_http.py`：`GET /api/chat/sessions` 只读端点，按 `x-qagent-tenant` 分桶，标题过 `redact_customer_text`。没有 switch，没有新写路径（POST 该路径 404）。
- 脸：右轨底加「对话」列（`session-face`），行 = 标题 + `当前 / 已清 · 时间`，当前那条左边描 ion 色。只读记录，没有点击跳转——不是房间。`paintSessions` 挂在 `refreshInbox` 第五段，boot / 发送后 / 新对话后随之刷新。

## 验证

- `tests/test_c01ae.py` 八项全绿，已挂 `run_tests.py`。
- 回归：`c01aa`、`c01z`、`c01y`、`c01ab`、`c01ac`、`c01ad`、`c01af`、`c01x`、`c01w`、`i01l` 全绿。
- 活验：3080 的 `/api/chat/sessions` 200，脸 HTML/JS/CSS 已带对话列，刷新即见。

## 没做的

- 切换对话、回看全文：snapshot 折不出全文，做了就是假装。列为后续候选波（新 fold + 切换写路径）。
- 标题不存用户原文以外的任何东西；句柄不进标题（HTTP 层统一遮）。
