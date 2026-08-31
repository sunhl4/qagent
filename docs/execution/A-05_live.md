# A-05-live · 活目录诚实记录

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | S1 · A-05-live |
| 范围 | 只本笔记 + `qagent/tests/test_a05_live.py` |
| 未改 | `qagent/src/**` · `test_a05.py` · `run_tests.py` · `PROGRESS.md` · chat / customer-shell / ionstack |
| 状态 | 对着真实 qdata home 的活目录 **未打**。活列表 **未证明**（unproven） |

## 产品锁

- 离线 `qdata_list_assets` 已由 [A-05](A-05_catalog.md) 覆盖：短列表，合计 ≤20，无 Pauli 全文，不发 `twin_id`。那是本地 store，**不是**活 home。
- 活目录 **未证明**，除非本笔记抄到一次真实 `qdata assets --store …`（或活 `GET /v1/assets`）输出，且只记行数 / 短名，不抄 Pauli。
- checkout 在场、`--help`、死 URL、离线 `qdata_list_assets` 绿，都不是活通。
- 不铸 `twin_id`。句柄只有 `circuit_id` / `asset_id` / `twin_id`。目录不发 `twin_id`。
- **不许**说「活目录已通」。没有活列表就不许改口。
- 默认测例只读本笔记。活探函数存在，但除非 `QAGENT_LIVE_QDATA=1` **且** home/URL 真通，否则不调用。

## 活列表规则

对着真实 qdata home 列目录 **未证明**（unproven）。没有真实 `qdata assets` / `GET /v1/assets` 就写「活目录已通」是造假。离线 A-05 短列表不是活目录。

活探若真跑通：只记 `length ≤ 20`，行键最多 `kind` / `name` / `asset_id`。不抄 `pauli_terms` / bitstrings / QASM / `summary` 全文。不铸 `twin_id`。

## 2026-08-27 本轮记录

`QAGENT_LIVE_QDATA` **未设**。按合同 **未打** `qdata assets --store`，**未打** 活 `GET /v1/assets`。**不许**说「活目录已通」。

| 检查 | 结果 |
|------|------|
| `QAGENT_LIVE_QDATA` | **未设** |
| `QAGENT_QDATA_HOME` | **未设** |
| `QAGENT_QDATA_BIN` | **未设** |
| `QAGENT_QDATA_URL` | **未设** |
| PATH `qdata` | **无**（`qdata not found`） |
| checkout `/Users/shl/nvidia/qdata` | **在**。`.venv/bin/qdata` 可执行（322 B，2026-08-11）。本轮未 export HOME，不算已通 |
| `qdata --help` | 子命令含 `assets`。这是 help，**不是** 活列表 |
| `qdata assets --help` | `usage: qdata assets [-h] --store STORE`。这是 help，**不是** `qdata assets --store` |
| `GET http://127.0.0.1:8787/v1/assets` | **不通**（根路径已失败） |
| 离线 `qdata_list_assets` | A-05 已有。本地 store，**不是** 活 home |
| 活列表 length | **无**。未打，不编 ≤20 |
| Pauli 全文 | **无**。不抄 |
| `twin_id` | **无**。不铸 |

`:8787` 原文（`curl -sS -m 2`）：

```
curl: (7) Failed to connect to 127.0.0.1 port 8787 after 0 ms: Couldn't connect to server
http_code=000
```

`--help` 原文（不是活列表，没有 length）：

```
usage: qdata [-h] {run,submit,assets,serve,mcp} ...
qdata — quantum data SDK
```

```
usage: qdata assets [-h] --store STORE
```

本轮没有活列表，所以对着真实 qdata home 的目录 **未证明**。离线短列表仍归 A-05。

## 未做

- 不改 `qdata.py` / `homes.py` / `run_tests.py` / `PROGRESS.md` / `test_a05.py` / customer-shell / `chat.py` / ionstack。
- 不启动 `scripts/start_qdata.sh`（要人设 `QAGENT_QDATA_HOME`）。
- 不把 checkout 在场、`--help`、或离线 `qdata_list_assets` 写成已通。
- 不调 `ionstack_twin_run`。不发明第四句柄。不抄 Pauli 全文。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_a05.py
PYTHONPATH=src python3 tests/test_a05_live.py
```

活探（可选，且 HOME 或 URL 必须真通）：

```bash
cd /Users/shl/nvidia/qagent
export QAGENT_LIVE_QDATA=1
export QAGENT_QDATA_HOME=/Users/shl/nvidia/qdata
# 或：已在跑的 serve → export QAGENT_QDATA_URL=http://127.0.0.1:8787
PYTHONPATH=src python3 tests/test_a05_live.py
```

缺 flag、缺 home、URL 不通、CLI 失败、没有可列的 store：打印 skip，退出 0。不发明活 length。不铸 `twin_id`。不抄 Pauli。没有活输出就不许写「活目录已通」。
