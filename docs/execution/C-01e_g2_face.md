# C-01e · G0 / G2 脸剩余

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P |
| 范围 | `qagent/apps/customer-shell/*` · `qagent/tests/test_c01e.py` |
| 状态 | 代码落地，文本测绿。不算过门。 |

## 产品锁

- **G0 脸**：开机读 workplace。`ready` 为假时打开 `#settings`（`showModal`）。`ready` 为真不自动开。对话若带回 `open_settings: true` 且仍未就绪，再开一次。字段暂缺时，开机这条仍走。
- **健康行**：`#health-line` 在就绪时可写公开 `llm_model` 名。不画 `llm_api_key` / `hpc_secret` / `quantum_secret`。
- **G2 回执**：`#receipt-list` 里只有 `signed` 行有下载 / 核验。下载 `GET /api/assignments/{id}/receipt` 存短 JSON（不指望电路正文）。核验 `POST /api/receipts/verify`，脸上写 ok / fail。未签收仍不盖绿印（R-03c）。
- `?role=customer` 仍藏 `#secret-fieldset`。IME / `aria-busy` / 无 document keydown 不动。没有三房间、Finder、`btn-twin`。

## 不做什么

不改 `qagent/src/**`（`open_settings` 由 chat 另包补）。不改 `chat.py` / `dsh_session.py`。不加第三套 agent loop。不编造 `twin_id`。不 commit。`run_tests.py` / `PROGRESS.md` 留给调度挂。本包只补 3080 脸，不是 G0 / G2 过门声明。
