# A-03f · start_twin 读 homes

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | A-03f |
| 范围 | `qagent/scripts/start_twin.sh` · `qagent/tests/test_a03f.py` |
| 未改 | `invoke.py` · ionstack adapter · `start_runtime.sh` · `run_tests.py` · `PROGRESS.md` · `PARALLEL.md` |
| 状态 | 空的 `QAGENT_IONSTACK_HOME` 先 source `dsh.env`，仍空则从 `workplace.json` 的 `ionstack_home` 补 export。**不算接线**。不算活 Twin 已通。不铸 `twin_id`。 |

H-03f 把设置里的 `ionstack_home` 写进 `dsh.env`。H-03g 让 `start_runtime.sh` 冷启动能看见。`start_twin.sh` 以前只认当时的 `QAGENT_IONSTACK_HOME`，人填了 3080 设置再跑本脚本仍 `exit 1`「set QAGENT_IONSTACK_HOME」。本包只改启动脚本：仍 `exec ionstack-serve`，loopback `:8765`。

## 写到哪里

- 脚本开头算 `QAGENT_ROOT`。
- 若 `QAGENT_IONSTACK_HOME` 已非空：**不覆盖**（不 source 冲掉，workplace 也不写回）。
- 若空：先 source `${QAGENT_ROOT}/.qagent/dsh.env`（文件在才 source）。仍空，则从 `${QAGENT_ROOT}/.qagent/workplace.json`（或已 export 的 `QAGENT_WORKPLACE_FILE`）读 `ionstack_home` → `QAGENT_IONSTACK_HOME`。
- 一小段 `python3 -` 只 print `KEY=value` 安全行（值里不要换行），再 `export`。不 `source` JSON 任意文本。
- 补完仍空：`exit 1`，句子仍是 `set QAGENT_IONSTACK_HOME to the ionstack checkout`。无 home / 无 bin 仍诚实失败。
- **永不**读 `secrets.json`。**永不** export `QAGENT_CLOUD_URL` / `hpc_secret` / `quantum_secret` / `llm_api_key`。不编假 `twin_id`。不编 `accepted:true`。
- 仍 `exec ionstack-serve --host 127.0.0.1 --port 8765`。不算接线。不算 G0。

不铸 `twin_id`。只有 `circuit_id` / `asset_id` / `twin_id`。无第四句柄。不调 TwinRun。不接线 Pennylane。不扩第三套 loop。

## 诚实

这是 **start_twin 读 homes**，让人填进设置的 `ionstack_home` 能被启动脚本看见。**不算接线**。**不算活 Twin 已通**。无 home 仍诚实 `exit 1`。exec 到不存在的 bin 仍失败。没有 TwinRun，没有 `twin_id`。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_a03f.py
```

不真的起 Twin。抽 python 片段 + 源码断言。

- 临时 workplace 有 `ionstack_home`、空 env → 得到 `QAGENT_IONSTACK_HOME`。
- env 已有 `QAGENT_IONSTACK_HOME` → 不被 workplace 覆盖。

## 不做

- 不改 `invoke.py` / ionstack adapter / `start_runtime.sh` / `run_tests.py` / PROGRESS / PARALLEL。
- 不 commit。
