# I-03 · ELN 事件与回放

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-26 |
| 角色 | A2 |
| 范围 | `models/eln.py` · `services/eln.py` · `adapters/eln.py` · `tests/test_i03.py` |
| 状态 | 代码落地，文本测绿 |

## 产品锁

- 五类短事件：`recipe_pin` / `estimate` / `twin_signoff` / `b3` / `assignment`。另留 `EVENT_CLAIM_BLOCKED`（`qagent/claim_blocked`），JSONL 仍是一行 `{type, **payload}`，`sort_keys=True`。
- 科学真源仍是 qdata。ELN 只记短字段。Pauli / bitstrings / cal / shuttle / qasm / 密钥键不落盘。
- `replay(assignment_id)`（`read_eln(assignment_id=…)` 同滤）按交办重建顺序。同 id 再读，字段集合不变。
- fork 复制该交办事件到新 `assignment_id`，**一律丢掉 `twin_id`**（与 `assignment.fork` 一致）。再写一条 assignment，带 `parent_assignment_id`。不铸 `twin_id`。
- dsh session fork 是后话。这里不碰 `dsh_session.py`，不新开 agent loop。

## 写到哪里

- `NativeEln` 认 `QAGENT_ELN_FILE`，默认仍 `.qagent/eln.jsonl`。每次 append/read 现取路径，测试可隔离。
- `short_payload` 递归去掉 `FORBIDDEN_ELN_KEYS` 与三枚密钥键。
- `append_*` 可带可选 `assignment_id`；既有 `invoke` / `assignment._persist` 调用不用改。

## 不做什么

不改 `run_tests.py` / `PROGRESS.md` / `chat.py` / `dsh_session.py` / `qdata.py` / customer-shell / `product_eval.py` / `ionstack.py` / `assignment.py`。不 commit。不 `import qdata`。

## 测

`qagent/tests/test_i03.py`：隔离 `QAGENT_ELN_FILE`；五类可写；禁键与密钥值被剥；同 `assignment_id` 回放字段集合一致；fork 无 `twin_id`、有父交办。

```text
PYTHONPATH=src python3 tests/test_i03.py
PYTHONPATH=src python3 tests/run_tests.py
```

`run_tests.py` 的 `test_ports` 仍用 `EVENT_CLAIM_BLOCKED` + `read_eln()` 断言 Aer 冒领被记。
