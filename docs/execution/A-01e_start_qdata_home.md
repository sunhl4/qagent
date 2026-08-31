# A-01e · start_qdata 读 homes

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | S1 · A-01e |
| 范围 | `qagent/scripts/start_qdata.sh` · `qagent/tests/test_a01e.py` |
| 未改 | `invoke.py` · `homes.py` · `workplace_store.py` · `start_runtime.sh` · `run_tests.py` · `PROGRESS.md` · `PARALLEL.md` |
| 状态 | 空的 `QAGENT_QDATA_HOME` 可从 `dsh.env` / `workplace.json` 的 `qdata_home` 补 export。**不算接线**。**不算活 qdata 已通**。无 bin 仍诚实失败。 |

H-03f 把 3080 设置里的 `qdata_home` 写入 `dsh.env`。H-03g 让 `start_runtime.sh` 冷启动也能读 `workplace.json`。本脚本以前只认当时的 `QAGENT_QDATA_HOME`，人填了设置再跑 `start_qdata.sh` 仍 `exit 1`「set QAGENT_QDATA_HOME」。本包只改启动脚本：仍 `exec qdata serve`，loopback。

## 写到哪里

- `start_qdata.sh`：若 `QAGENT_QDATA_HOME` **已非空**，**不覆盖**。
- 若空：先 source `${QAGENT_ROOT}/.qagent/dsh.env`（文件在才 source）。
- source 后仍空：从 `${QAGENT_WORKPLACE_FILE}` 或 `${QAGENT_ROOT}/.qagent/workplace.json` 读 `qdata_home` → `export QAGENT_QDATA_HOME`。
- 一小段 `python3 -` 只 print `KEY=value` 安全行（值里不要换行），再 `export`。不 `source` JSON 任意文本。坏 JSON / 无文件 / 字段空：安静跳过。
- 补完仍空：`exit 1`，句子仍是 `set QAGENT_QDATA_HOME to the qdata checkout`。无 bin：`qdata CLI missing at ...`。
- **永不**读 `secrets.json`。**永不** export `QAGENT_CLOUD_URL` / `hpc_secret` / `quantum_secret` / `llm_api_key`。只认 `qdata_home`。
- 仍 `exec qdata serve --host 127.0.0.1`。不算接线。不算 G0。

不铸 `twin_id`。只有 `circuit_id` / `asset_id` / `twin_id`。无第四句柄。不调 TwinRun。不接线 Pennylane。不发明 `status=done`。

## 诚实

这是 **start_qdata 读 homes**，让人填了 3080 设置之后本脚本能看见 `qdata_home`。**不算接线**。**不算活 qdata 已通**。checkout 在场、`--help`、补到了 HOME，都不是活通。无 bin 仍诚实失败。活 `qdata run` / 活 HTTP 仍归 A-01 / A-01-live。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_a01e.py
```

不真的 `exec qdata`。抽 HOMES python：

- 空 env + workplace 有 `qdata_home` → 得到 `QAGENT_QDATA_HOME`。
- env 已有 → 不覆盖。
- 无 home → 脚本仍含诚实失败句。

## 不做

- 不改 `invoke.py` / `homes.py` / `workplace_store.py` / `start_runtime.sh`。
- 不 commit。`run_tests.py` / `PROGRESS.md` / `PARALLEL.md` 留给调度。
- 不宣称活 qdata 已通。
