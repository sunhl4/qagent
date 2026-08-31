# H-03f · homes 进 dsh.env

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | A1 · H-03f |
| 范围 | `adapters/workplace_store.py` · `qagent/tests/test_h03f.py` |
| 未改 | `services/workplace.py` · customer-shell · `run_tests.py` · `PROGRESS.md` · `PARALLEL.md` |
| 状态 | save 后有值的 home 进 `.qagent/dsh.env`。**不算接线**。不算 G0/G2。 |

3080 设置里的 `qdata_home` / `qchem_home` / `ionstack_home` / `knowledge_path` 经 `apply_env()` 只进 **3080 进程**。`start_runtime.sh` source 的是 `.qagent/dsh.env`，以前只有 `DEEPSEEK_*`，dsh 脑（3081）看不见 HOME。活 A-01 以后填了设置仍找不到 `qdata`。

## 写到哪里

- `WorkplaceStore.save()` → `write_dsh_env`：字段有值才写一行
  - `QAGENT_QDATA_HOME`
  - `QAGENT_QCHEM_HOME`
  - `QAGENT_IONSTACK_HOME`
  - `QAGENT_KNOWLEDGE_PATH`
- 空字段：不写该行，不留空赋值。换值再 save：旧路径从 `dsh.env` 消失。
- `cloud_url` **永不**进 `dsh.env`（C-03）。`hpc_secret` / `quantum_secret` **永不**进（I-02）。
- `llm_api_key` 仍镜像 `DEEPSEEK_API_KEY`。`DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL` 保持。
- 不铸 `twin_id`。只有 `circuit_id` / `asset_id` / `twin_id`。无第四句柄。不调 TwinRun。不接线 Pennylane。

## 诚实

这是 **homes 进 dsh.env**，让 3081 能看见设置里的路径。**不算接线**。不算活 A-01。不算 G0/G2。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_h03f.py
PYTHONPATH=src python3 tests/test_h03.py
PYTHONPATH=src python3 tests/test_c03.py
PYTHONPATH=src python3 tests/test_i02.py
```

- save 四个路径 → `dsh.env` 四行都在且值对。
- 清空其中一个再 save → 该行消失。
- 带 `cloud_url` + `hpc_secret` → 无 `QAGENT_CLOUD_URL`、无密钥原文。

## 不做

- 不改 workplace 服务层、脸、`run_tests.py`、PROGRESS、PARALLEL。
- 不 commit。
