# I-03h · GET /api/eln 带回 claim_blocked 的 reason

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | A2 |
| 范围 | `tests/test_i03h.py` · 本笔记 · `INTERFACES.md` 半句 |
| 状态 | 现有 GET 已带回 reason，本包只加测与文档。不算过门。 |

## 产品锁

- 隔离 ELN 文件后 `append_claim_blocked(reason="cirq_claim_twin_id")`，再 `GET /api/eln`。
- `{events}` 里有 `type=qagent/claim_blocked`（或等价），且 **reason 字段在**：顶层 `reason` 或 `payload.reason`。
- 回显前仍走已有 `short_payload`。`reason` 不在剥除键里，GET **没有**丢掉它。本包不改 `src` 业务逻辑。
- 无 POST：`POST /api/eln` 仍 404、不写盘。追加只在 services。
- 无密钥、无电路正文回显。不铸 `twin_id`。无第四句柄。
- `dispatch()` 不写本地 `status =`（`chat_status` 导入名不动）。

## 写到哪里

- 新测 `qagent/tests/test_i03h.py`：隔离文件、append、GET、reason 在、POST 不追加、误种密钥/正文被剥且 reason 仍在。
- `INTERFACES.md` ELN 只读行补「`claim_blocked` 带短 `reason`」。
- 未改 `shell_http.py` / `services/eln.py` / `models/eln.py`。GET 已是 `read_eln` + `short_payload`。

## 不做什么

不改 `run_tests.py` / `PROGRESS.md` / `test_i03.py` / `test_i03d.py` / `test_i03f.py` / customer-shell / `eln.md` / knowledge。不加 POST 追加。不 commit。不 `import qdata`。本包只证明 HTTP 带回短 reason，**不算** G2。

## 测

`qagent/tests/test_i03h.py`：`append_claim_blocked(reason="cirq_claim_twin_id")` 后 GET 见 `qagent/claim_blocked` 且 reason 在；嵌套 `payload.reason` 也在；盘上误种的密钥与电路正文被剥、reason 留下；POST 404 且不写盘。`test_i03d` / `test_i03f` 仍绿。

```text
PYTHONPATH=src python3 tests/test_i03h.py
PYTHONPATH=src python3 tests/test_i03d.py
PYTHONPATH=src python3 tests/test_i03f.py
```
