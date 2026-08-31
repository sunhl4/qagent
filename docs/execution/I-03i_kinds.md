# I-03i · ELN 规范种类含 claim_blocked

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | A2 |
| 范围 | `models/eln.py` · `tests/test_i03.py` · `tests/test_i03i.py` |
| 状态 | 代码落地，文本测绿。不算过门。 |

## 产品锁

- `ELN_EVENT_KINDS` 在原五类之后加上 `EVENT_CLAIM_BLOCKED`（`qagent/claim_blocked`）。现列表：`recipe_pin` / `estimate` / `twin_signoff` / `b3` / `assignment` / `claim_blocked`。
- 整组回放写入 `_append_kinds`（旧名 `_append_five` 仍包装），含 `append_claim_blocked`。`replay` 类型列表仍等于 `ELN_EVENT_KINDS`。
- `short_payload` 仍剥密钥键与电路正文。fork 仍丢掉 `twin_id`，再写 assignment 带 `parent_assignment_id`。
- 不算 G2。不铸 `twin_id`。只有 ionstack TwinRun 能发 `twin_id`。

## 写到哪里

- `qagent/src/qagent/models/eln.py`：`ELN_EVENT_KINDS` 第六项为 `EVENT_CLAIM_BLOCKED`。
- `qagent/tests/test_i03.py`：回放组带 `append_claim_blocked`。
- `qagent/tests/test_i03i.py`：种类序、回放等于种类、fork 仍无 `twin_id`。

## 不做什么

不改 customer-shell、`eln.md`、`INTERFACES.md`、`test_i03d` / `e` / `f` / `g`、`run_tests.py`、`PROGRESS.md`、knowledge、`shell_http.py`。不改 `services/eln.py`。不 commit。

## 测

`qagent/tests/test_i03.py`：种类回放含 `claim_blocked`；禁键与密钥仍剥；fork 无 `twin_id`。`test_i03d.py` 仍绿。

```text
PYTHONPATH=src python3 tests/test_i03.py
PYTHONPATH=src python3 tests/test_i03d.py
PYTHONPATH=src python3 tests/test_i03i.py
```
