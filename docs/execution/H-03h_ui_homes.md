# H-03h · start_ui 读 homes

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | A1 · H-03h |
| 范围 | `qagent/scripts/start_ui.sh` · `qagent/tests/test_h03h.py` |
| 未改 | `workplace_store.py` · `invoke.py` · `homes.py` · `chat.py` · `agent.py` · `run_tests.py` · `PROGRESS.md` · `PARALLEL.md` |
| 状态 | 3080 脸进程空的四个 HOME 从 `dsh.env` 再从 `workplace.json` 补 export。**不算接线**。不算 G0/G2。 |

H-03g 让 `start_runtime.sh` 冷启动能看见 `workplace.json` 里的路径。`start_qdata.sh` / `start_twin.sh` 也已补空 HOME。`start_ui.sh` 以前不读。3080 `serve()` 虽 `apply_env()`，本机 workplace 无 HOME 时 `GET /api/health` 的 `qdata_cli` / `qchem_live` 仍为 false（`twin_live` 已因 `:8765` 为 true）。本包只改脸启动脚本：仍 `exec python3 -m qagent.entrypoints.shell_cli --serve`。不要把 `dsh` 塞进 `start_ui`。

## 写到哪里

- `start_ui.sh`：若下列变量仍空，先从 `${QAGENT_ROOT}/.qagent/dsh.env` 只认这四行再 `export`，仍空则从 `${QAGENT_ROOT}/.qagent/workplace.json`（或已 export 的 `QAGENT_WORKPLACE_FILE`）读对应字段并 `export`：
  - `qdata_home` → `QAGENT_QDATA_HOME`
  - `qchem_home` → `QAGENT_QCHEM_HOME`
  - `ionstack_home` → `QAGENT_IONSTACK_HOME`
  - `knowledge_path` → `QAGENT_KNOWLEDGE_PATH`
- 环境里已有非空值：**不覆盖**（人 export 优先，其次 `dsh.env`，再 `workplace.json`）。
- 无 workplace 文件 / JSON 坏 / 字段空：安静跳过，不 exit。
- 一小段 `python3 -` 只 print `KEY=value` 安全行（值里不要换行），再 `export`。不 `source` JSON 任意文本。`dsh.env` 只扫四个 HOME 键，不 `source` 整文件。
- **永不**读 `secrets.json`。**永不** export `QAGENT_CLOUD_URL` / `hpc_secret` / `quantum_secret` / `llm_api_key`。
- 仍打 token / `role=customer` / 客户租户示例那几行。仍 loopback `127.0.0.1`。

不铸 `twin_id`。只有 `circuit_id` / `asset_id` / `twin_id`。无第四句柄。不调 TwinRun。不接线 Pennylane。

## 诚实

这是 **start_ui 读 homes**，让冷启动 3080 看见 `dsh.env` / 旧 `workplace.json` 里的路径。**不算接线**。不算活 A-01。不算 G0/G2。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_h03h.py
PYTHONPATH=src python3 tests/test_o01e.py
PYTHONPATH=src python3 tests/test_o01h.py
```

- 临时 workplace 有 `qdata_home`、空 env → 得到 `QAGENT_QDATA_HOME`。
- `dsh.env` 有 HOME、workplace 另有值 → `dsh.env` 先补，workplace 不覆盖已补的。
- env 已有 `QAGENT_QDATA_HOME` → 不被 `dsh.env` / workplace 覆盖。
- workplace 有 `cloud_url` + 密钥键 → 输出不含 `QAGENT_CLOUD_URL` / 密钥。

## 不做

- 不改 `workplace_store.py` / `invoke.py` / `homes.py` / `chat.py` / `agent.py`。
- 不 commit。`run_tests.py` / `PROGRESS.md` / `PARALLEL.md` 留给调度。
- 不宣称过门。不 pkill dsh。
