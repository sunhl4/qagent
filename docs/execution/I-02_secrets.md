# I-02 · 密钥不进模型上下文

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-26 |
| 角色 | P+S1 |
| 范围 | `services/workplace.py` · `adapters/workplace_store.py` · `tests/test_i02.py` |
| 状态 | 代码落地，文本测绿 |

## 产品锁

- 密钥只有三枚：`llm_api_key` / `hpc_secret` / `quantum_secret`。落在 `secrets.json`，模式 **0600**。
- GET / `workplace_status` / `to_public` 只有 `has_*`。JSON 里不能出现密钥**值**。
- `chat.turn` 只把人话交给 `session.prompt`。不把 workplace / secrets 拼进 dsh content。
- 提交 job **可以用**密钥做本地 HTTP `Authorization`。invoke 回给模型的 payload 不许带值。`qdata.py` 当前不读密钥，没有往 prompt 里倒。

## 写到哪里

- `WorkplaceStore.load` 读 public 时丢掉密钥字段；每次 load 把 secrets 文件锁回 0600。
- `WorkplaceStore.local_auth_headers` / `job_auth_headers` 只给南向 HTTP。调用方不得把这张表送进 status 或 dsh prompt。
- `apply_env` 只把 `llm_api_key` 镜像到进程里的 `DEEPSEEK_API_KEY`（dsh / 本地模型 HTTP）。超算 / 量子口令不进 env。
- `workplace_status` 在 `to_public` 之后再扫一遍，去掉误入的密钥字段和值。
- `chat.py` 未改：approve / respond 不动；prompt 仍是用户那一句。

## 不做什么

不改 `run_tests.py` / `PROGRESS.md` / customer-shell / `product_eval.py` / `assignment.py` / `ionstack.py` / `agent.py`。不 commit。不把真实 `secrets.json` 读进模型上下文。

## 测

`qagent/tests/test_i02.py`：种三枚口令后，`workplace_status` JSON 没有值；假 transport 下 `session.prompt` 没有值；`workplace.py` + `chat.py` 源码不把 secrets 格式化进 dsh 字符串。

```text
PYTHONPATH=src python3 tests/test_i02.py
PYTHONPATH=src python3 tests/run_tests.py
```
