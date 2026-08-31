# H-03e · 下一句公开模型名

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | A1 · H-03e |
| 范围 | `workplace_status` 增加短字段 `next_model` · `tests/test_h03e.py` |
| 未改 | customer-shell · `run_tests.py` · `PROGRESS.md` · `test_h03.py` · `test_h03d_live.py` · `chat.py` · `dsh_session.py` · workplace store · 密钥文件 |
| 状态 | status JSON 可给脸读下一句公开模型名。**不许**说「活模型切换已通」 |

`GET /api/workplace` 已经回公开 `llm_model`。本包只在 `workplace_status()` 顶层再放一个短 `next_model`，等于公开 `llm_model`；未就绪则为空串。脸可以用它说出下一句人话打算用哪个模型。

## 写到哪里

- `workplace_status()`：`next_model` = `to_public()` 的 `llm_model`；`ready()` 为假则为 `""`。
- 仍走 `_without_secret_values`。JSON **没有** `llm_api_key` / `hpc_secret` / `quantum_secret` 键或值，只有 `has_*`。
- 不铸 `twin_id`。不发明第四句柄。不调 `ionstack_twin_run`。

## 诚实

这是公开模型名的回显，不是活 dsh 换模证明。H-03c 已把 workplace 模型写入进程 `DEEPSEEK_MODEL`；H-03d-live 仍记「活切换未打」。本包**不**声称下一句人话已经按新模型走。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_h03e.py
PYTHONPATH=src python3 tests/test_h03.py
PYTHONPATH=src python3 tests/test_o01b.py
```

- 已设且就绪：`next_model` 等于公开 `llm_model`。
- 未就绪：`next_model` 为空。
- 密钥键缺席；GET 仍只用 `has_*` 表示密钥在不在。

## 不做

- 不改 customer-shell（C-01e 可自己读 `llm_model`）。
- 不改 `chat.py` / `dsh_session.py` / 密钥文件。
- 不 commit。`run_tests.py` / `PROGRESS.md` 留给调度。
