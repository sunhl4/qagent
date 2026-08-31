# I-01c · 3080 在办

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-26 |
| 角色 | P |
| 范围 | `qagent/apps/customer-shell/*` · `qagent/tests/test_i01c.py` |
| 状态 | 代码落地，文本测绿 |

## 产品锁

- 3080 主面仍是对话。在办是一条可见列表，不是三房间，也不是 recipe 下拉。
- ask 条只画短 `assignment_id`、工具名、`needs_ask`。预检只读 `GET …/preflight` 的布尔检查，不回显 identity / 密钥。
- 「批准上机 / 先不上机」仍走已有 `send("批准")` / `send("先不批")` 和 token 头。不 `POST /api/assignments/{id}/approve`，不新开 loop。
- `GET /api/assignments?status=needs_ask` 跟 `/api/chat/status` 一起偶发刷新；空列表写「现在没有待拍板的上机」，不假装已经在算。
- `aria-busy` 仍在 `#stage`。Enter 只在输入框自己身上发送，轮询重画在办时不抢焦点。

## 不做什么

不改 `chat.py` / `dsh_session.py` / `assignment.py` / workplace。不加 dsh 工作区门槛。不显示密钥。不 commit。`run_tests.py` / `PROGRESS.md` 留给调度挂。
