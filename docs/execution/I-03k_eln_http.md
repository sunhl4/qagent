# I-03k · ELN GET 不泄 twin_id

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | A2 |
| 范围 | `entrypoints/shell_http.py` · `tests/test_i03k.py` · 本笔记 |
| 状态 | 代码落地，文本测绿。不算过门。不算接线。 |

## 产品锁

- `GET /api/eln` 仍只读。回显改为 `short_payload(drop_twin(row))`。**不泄 twin_id**。
- **不**改 `short_payload()` 本身。`append_*` 仍用它落盘；`append_twin_signoff` **盘上可留**真 TwinRun `twin_id`。
- HTTP 仍有 `type`、`assignment_id`；`recipe` / `params.shots` / `reason` 保持（I-03d / I-03f / I-03h）。
- 无电路正文 / qasm / 三枚密钥键回显。无 POST：`POST /api/eln` 仍 404。
- 不铸 `twin_id`。无第四句柄。不算 G2。不算接线。

## 写到哪里

- `qagent/src/qagent/entrypoints/shell_http.py`：`_eln_http` 先 `drop_twin` 再 `short_payload`。
- `qagent/tests/test_i03k.py`：隔离 ELN、盘上签收可带 `twin_id`，GET 无泄漏。

## 不做什么

不改 `short_payload` / `append_*` / `services/eln.py` 落盘、`cards.py`、customer-shell、`run_tests.py`、`PROGRESS.md`、`PARALLEL.md`。不接线 Pennylane。不 commit。不 `import qdata`。本包只堵 HTTP ELN 读面，**不算** G2。

## 测

`qagent/tests/test_i03k.py`：`append_twin_signoff(twin_id=...)` 后盘上 jsonl 有 `twin_id`；`GET /api/eln` 无 `twin_id` / body / qasm / 密钥，仍有 `type` + `assignment_id`；笔记写明不算 G2、不泄 `twin_id`、盘上可留。`test_i03d` / `test_i03f` / `test_i03h` / `test_i03j` 仍绿。

```text
PYTHONPATH=src python3 tests/test_i03k.py
PYTHONPATH=src python3 tests/test_i03d.py
PYTHONPATH=src python3 tests/test_i03h.py
```
