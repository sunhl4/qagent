# H-03g · start_runtime 读 workplace homes

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | A1 · H-03g |
| 范围 | `qagent/scripts/start_runtime.sh` · `qagent/tests/test_h03g.py` |
| 未改 | `workplace_store.py` · `invoke.py` · `homes.py` · `run_tests.py` · `PROGRESS.md` · `PARALLEL.md` |
| 状态 | 冷启动 source `dsh.env` 之后，空的四个 HOME 从 `workplace.json` 补 export。**不算接线**。不算 G0/G2。 |

H-03f 只在 **save** 后把 homes 写入 `dsh.env`。H-03f **之前**就写进 `workplace.json` 的 `qdata_home` / `qchem_home` / `ionstack_home` / `knowledge_path`，用户不再点保存时，`start_runtime.sh` 以前只 source `dsh.env`，3081 仍看不见。本包只改启动脚本：脑仍是 `dsh --profile qagent`。

禁止在 `invoke.py` 里 `apply_env()`：A-01 等测只 pop env，不隔离 `QAGENT_WORKPLACE_FILE`，一 apply 会从本机 workplace 把 HOME 灌回去。

## 写到哪里

- `start_runtime.sh`：source `.qagent/dsh.env` **之后**，若下列变量仍空，从 `${QAGENT_ROOT}/.qagent/workplace.json`（或已 export 的 `QAGENT_WORKPLACE_FILE`）读对应字段并 `export`：
  - `qdata_home` → `QAGENT_QDATA_HOME`
  - `qchem_home` → `QAGENT_QCHEM_HOME`
  - `ionstack_home` → `QAGENT_IONSTACK_HOME`
  - `knowledge_path` → `QAGENT_KNOWLEDGE_PATH`
- 环境里已有非空值：**不覆盖**（`dsh.env` / 人 export 优先）。
- 无 workplace 文件 / JSON 坏 / 字段空：安静跳过，不 exit。
- 一小段 `python3 -` 只 print `KEY=value` 安全行（值里不要换行），再 `export`。不 `source` JSON 任意文本。
- **永不**读 `secrets.json`。**永不** export `QAGENT_CLOUD_URL` / `hpc_secret` / `quantum_secret` / `llm_api_key`。
- 仍 `exec dsh --profile qagent`。

不铸 `twin_id`。只有 `circuit_id` / `asset_id` / `twin_id`。无第四句柄。不调 TwinRun。不接线 Pennylane。

## 诚实

这是 **start_runtime 读 workplace homes**，让冷启动 3081 看见旧 `workplace.json` 里的路径。**不算接线**。不算活 A-01。不算 G0/G2。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_h03g.py
```

- 临时 workplace 有 `qdata_home`、空 env → 得到 `QAGENT_QDATA_HOME`。
- env 已有 `QAGENT_QDATA_HOME` → 不被 workplace 覆盖。
- workplace 有 `cloud_url` + 密钥键 → 输出不含 `QAGENT_CLOUD_URL` / 密钥。

## 不做

- 不改 `workplace_store.py` / `invoke.py` / `homes.py`。
- 不 commit。`run_tests.py` / `PROGRESS.md` / `PARALLEL.md` 留给调度。
