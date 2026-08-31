# I-03d · ELN 只读 HTTP

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | A2 |
| 范围 | `entrypoints/shell_http.py` · `tests/test_i03d.py` · `INTERFACES.md` 一行 |
| 状态 | 代码落地，文本测绿 |

## 产品锁

- `GET /api/eln` → `{events: [...]}`。只读，走已有 `read_eln()`。
- 可选 `?assignment_id=`，同一过滤：`read_eln(assignment_id=)`。
- 回显前再跑 `short_payload`：三枚密钥键与电路正文（`body` / `qasm3` 等禁键）若出现则剥掉。
- **没有** `POST /api/eln`。追加仍只在 services（`append_recipe_pin` / `append_estimate` / …）。
- 不铸 `twin_id`。pin / estimate 的 GET 里没有。fork 仍丢掉 `twin_id`（I-03 已做）。
- `dispatch()` 不写本地 `status =`（`chat_status` 导入名不动）。不扩 `agent.py`。

## 写到哪里

- `dispatch` 增加 GET `/api/eln`，委托 `_eln_http(query)`。
- `do_GET` 把完整 `self.path`（含 query）交给 `dispatch`，这样真 HTTP 的 `?assignment_id=` 也能滤。
- 服务层、`eln.py`、customer-shell、chat、dsh session 未改。

## 不做什么

不改 `run_tests.py` / `PROGRESS.md` / `test_i03.py` / customer-shell / `chat.py` / `dsh_session.py` / `eln.py`。不加 POST 追加。不 commit。不 `import qdata`。

## 测

`qagent/tests/test_i03d.py`：空列表；pin+estimate 可见且无 `twin_id` / `hpc_secret`；`assignment_id` 过滤；盘上误种的密钥与电路正文被剥；POST 404 且不写盘。`test_i03.py` 仍绿。

```text
PYTHONPATH=src python3 tests/test_i03d.py
PYTHONPATH=src python3 tests/test_i03.py
```
