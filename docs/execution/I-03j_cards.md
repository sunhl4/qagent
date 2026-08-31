# I-03j · cards 不泄 twin_id

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | A2 |
| 范围 | `services/cards.py` · `tests/test_i03j.py` · 本笔记 |
| 状态 | 代码落地，文本测绿。不算过门。不算接线。 |

## 产品锁

- `pes_card()` / `signoff_card()` 仍回 `kind=pes` / `kind=signoff`。
- 嵌套最后一条 `recipe_pin` / `twin_signoff` / `b3` 先 `drop_twin` 再 `short_payload`，再只留 `type` + 短 `assignment_id` + 非句柄摘要（`recipe` / `shots_actual` / `verdict`）。不要整份 raw event。
- `GET /api/cards` 因此无 `twin_id`、无 circuit body / qasm / counts、无三枚密钥键。不泄 `twin_id`。
- 不改 `GET /api/eln`、`eln.py`、`shell_http.py`、customer-shell。3080 脸仍不走 `/api/cards`。
- 不铸 `twin_id`。无第四句柄。不算 G2。不算接线。

## 写到哪里

- `qagent/src/qagent/services/cards.py`：最后一条事件洗面后再进卡片。
- `qagent/tests/test_i03j.py`：隔离 ELN、盘上可带 `twin_id` 的签收，卡片与 GET 无泄漏。

## 不做什么

不改 `shell_http.py` / `services/eln.py` / `models/eln.py` / customer-shell / `run_tests.py` / `PROGRESS.md`。不接线 Pennylane。不 commit。不 `import qdata`。本包只堵 HTTP 卡片读面，**不算** G2。

## 测

`qagent/tests/test_i03j.py`：append 带 `twin_id` 的 `twin_signoff`（正文/密钥走 jsonl），`pes_card` / `signoff_card` / `GET /api/cards` 无 `twin_id` / body / qasm / 密钥，仍有 kind；笔记写明不算 G2、不泄 `twin_id`。`test_i03d` / `test_i03h` 仍绿。

```text
PYTHONPATH=src python3 tests/test_i03j.py
PYTHONPATH=src python3 tests/test_i03d.py
PYTHONPATH=src python3 tests/test_i03h.py
```
