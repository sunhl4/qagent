# R-03c · 未签收脸

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-26 |
| 角色 | P |
| 范围 | `qagent/apps/customer-shell/*` · `qagent/tests/test_r03c.py` |
| 状态 | 代码落地，文本测绿 |

## 产品锁

- 回执 / 交办脸只看 `status`。不是 `signed` 就不能用已签收的颜色和标签：不盖绿印，不写「已签收」。
- `needs_ask`（在办条）走 `face-waiting`，标签仍是 `needs_ask`。`failed` / `rejected` 走 `face-stopped`（「已停」）。只有 `signed` 走 `face-signed` 绿印和「已签收」。
- `twin_id` 只在 `status=signed` 时画。静态 html 没有假句柄。`signoff.eligible` 不算封条。
- C-01 文案和 I-01c 在办不动：平常话、在办、批准上机 / 先不上机仍走 `send("批准")` / `send("先不批")`。空在办仍是「现在没有待拍板的上机」，空回执不写「已签收」。
- 回执列表另读 `GET /api/assignments`，在办仍读 `?status=needs_ask`。同一刷新，不新开 loop。

## 不做什么

不改 `chat.py` / `dsh_session.py` / `assignment.py` / workplace。不加第三套 agent loop。不 commit。`run_tests.py` / `PROGRESS.md` 留给调度挂。
