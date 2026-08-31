# I-03e · 3080 只读画 ELN

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P |
| 范围 | `qagent/apps/customer-shell/*` · `qagent/tests/test_i03e.py` |
| 状态 | 代码落地，文本测绿。不算过门。 |

## 产品锁

- 右侧 aside、回执下面加「实验记录 / ELN」：`#eln-face` / `#eln-list` / `#eln-empty`。
- 与在办、回执同一刷新：`boot` / `refreshInbox` 里 `GET /api/eln`，用已有 `headers()`。画 `{events}` 短列表。
- 每行只画短 `type`（`recipe_pin` / `estimate` / `twin_signoff` / `b3` / `assignment`）和交办号（payload 里有 `assignment_id` 才画）。字段用 `textContent`。
- 不画电路正文、`qasm3`、密钥键值（`hpc_secret` / `llm_api_key` / `quantum_secret`）。不铸 `twin_id`。
- 空列表诚实空文案「还没有实验记录。」，不编假事件。
- 没有 POST /api/eln。脸不追加、不写盘。若过滤，只能 `GET /api/eln?assignment_id=`；客户可见文案不写第四个句柄。
- 保持 C-01e：未就绪 `showModal`；对话 `open_settings` 且仍未就绪可再开；已签收回执下载 / 核验；`?role=customer` 仍藏 `#secret-fieldset`；IME / `aria-busy` 不动。没有三房间、Finder、`btn-twin`。

## 不做什么

不改 `qagent/src/**`、`chat.py`、`eln.py`、`shell_http.py`。不加 POST 追加。不编造 `twin_id`。不 commit。`run_tests.py` / `PROGRESS.md` / `PARALLEL.md` 留给调度。本包只画只读脸，**不算** G0 / G2 过门。

## 测

`qagent/tests/test_i03e.py`：区块 id；`GET` + `/api/eln`、无 `POST` + `/api/eln`；不渲染密钥 / `body` / `qasm3`；不宣称 G0/G2 通过；无三房间 / Finder。`test_c01e` / `test_c01d` / `test_i01c` / `test_r03c` 仍绿。

```text
PYTHONPATH=src python3 tests/test_i03e.py
PYTHONPATH=src python3 tests/test_c01e.py
PYTHONPATH=src python3 tests/test_c01d.py
PYTHONPATH=src python3 tests/test_i01c.py
PYTHONPATH=src python3 tests/test_r03c.py
```
