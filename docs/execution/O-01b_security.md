# O-01b · 安全冻结（密钥 / loopback / token）

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | A2 / O-01b |
| 范围 | `entrypoints/debug_gate.py` · `scripts/start_ui.sh` · `tests/test_o01b.py` |
| 状态 | 冻结测绿。I-02 已藏密钥，本包不抢 |

## 产品锁

- 上机 / 非回环绑定要带进程内 `QAGENT_SHELL_TOKEN`。`approved_allowed({}, True)` 无 token 为假；头 `X-QAGENT-DEBUG-TOKEN` 或 `X-QAGENT-APPROVE-TOKEN` 与环境变量一致才过。
- `bind_allowed("127.0.0.1")` 恒真。`0.0.0.0`（以及空 host）无 token 为假；有 token 才许非回环。空字符串不是 loopback：`HTTPServer(('', port))` 会听全部网卡。
- `start_ui.sh` 写死 `--host 127.0.0.1`，打印 `http://127.0.0.1:…`。
- `workplace_status` / `Workplace.to_public` 键不含 `llm_api_key` / `hpc_secret` / `quantum_secret`。值藏由 I-02 负责。
- 脑仍是 `dsh --profile qagent`。不加第三套 loop。不铸 `twin_id`。

## 写到哪里

- `bind_allowed` 去掉把 `""` 当回环的口子；host 先 `strip`。
- `start_ui.sh` 未改（本来就是 127.0.0.1）。
- 冻结测：`qagent/tests/test_o01b.py`（隔离 `QAGENT_SHELL_TOKEN` 与 workplace 文件）。

## 不做什么

不改 `run_tests.py` / `PROGRESS.md` / `workplace.py` / `workplace_store.py` / `chat.py` / `dsh_session.py` / assignment / customer-shell / I-02 测试。不 commit。不调 TwinRun。

## 测

```text
cd qagent
PYTHONPATH=src python3 tests/test_o01b.py
```
