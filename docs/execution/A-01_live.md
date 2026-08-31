# A-01-live · 活 qdata 诚实记录

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | S1 · A-01-live |
| 范围 | 只本笔记 + `qagent/tests/test_a01_live.py` |
| 未改 | `qagent/src/**`（适配器已 fail-close）· `test_a01.py` · `run_tests.py` · `PROGRESS.md` · chat / dsh / ionstack |
| 状态 | 活 `qdata run` / 活 HTTP **未打**。活 qdata **未证明**（unproven） |

## 产品锁

- 活 CLI / `:8787` **未证明**，除非本笔记抄到一次真实 `qdata run`（或活 HTTP）输出，且里面有 `asset_id`。
- 死 URL / 缺 bin 已由 [A-01](A-01_qdata_honesty.md) 覆盖，必须保持诚实。本包不重写那条失败，不改口。
- 不铸 `twin_id`。电路体 / QASM 不当句柄。句柄只有 `circuit_id` / `asset_id` / `twin_id`，qdata 只许出 `asset_id`。
- **不发明** `status=done`。本地卡 `qagent-local-card` 不是活 qdata。
- 默认测例只读本笔记。活探函数存在，但除非 `QAGENT_LIVE_QDATA=1` **且** home/URL 真通，否则不调用。

## 活 `asset_id` 规则

活 qdata **未证明**（unproven）。没有真实命令输出就写「活 qdata 已通」是造假。`--help`、checkout 在场、本地卡出的 `asset_id`、死 URL 抛错，都不是活通。

## 2026-08-27 本轮记录

`QAGENT_LIVE_QDATA` **未设**。按合同 **未打** `qdata run`，**未打** 活 HTTP job。**未写** `status=done`。**不许**说「活 qdata 已通」。

| 检查 | 结果 |
|------|------|
| `QAGENT_LIVE_QDATA` | **未设** |
| `QAGENT_QDATA_HOME` | **未设** |
| `QAGENT_QDATA_BIN` | **未设** |
| `QAGENT_QDATA_URL` | **未设** |
| PATH `qdata` | **无**（`qdata not found`） |
| checkout `/Users/shl/nvidia/qdata` | **在**。`.venv/bin/qdata` 可执行（322 B，2026-08-11）。本轮未 export HOME，不算已通 |
| `qdata --help` | 子命令 `run` / `submit` / `assets` / `serve` / `mcp`。这是 help，**不是** `qdata run` |
| `GET http://127.0.0.1:8787/` | **不通** |
| `qdata run <recipe>` | **未打** |
| 活 `POST /v1/jobs/{kind}` | **未打** |
| 活 `asset_id` | **无** |
| `status=done` | **未写** |
| `twin_id` | **无**。不铸 |
| 电路体当句柄 | **无** |

`:8787` 原文（`curl -sS -m 2`）：

```
curl: (7) Failed to connect to 127.0.0.1 port 8787 after 0 ms: Couldn't connect to server
http_code=000
```

`--help` 原文（不是 `qdata run`，没有 `asset_id`）：

```
usage: qdata [-h] {run,submit,assets,serve,mcp} ...
qdata — quantum data SDK
```

本轮没有活 `asset_id`，所以活 qdata **未证明**。死 URL / 缺 CLI 的诚实失败仍归 A-01。

## 未做

- 不改 `qdata.py` / `homes.py` / `run_tests.py` / `PROGRESS.md` / `test_a01.py` / customer-shell / `chat.py` / `dsh_session.py` / ionstack。
- 不启动 `scripts/start_qdata.sh`（要人设 `QAGENT_QDATA_HOME`）。
- 不把 checkout 在场或 `--help` 写成已通。
- 不调 `ionstack_twin_run`。不发明第四句柄。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_a01.py
PYTHONPATH=src python3 tests/test_a01_live.py
```

活探（可选，且 HOME 或 URL 必须真通）：

```bash
cd /Users/shl/nvidia/qagent
export QAGENT_LIVE_QDATA=1
export QAGENT_QDATA_HOME=/Users/shl/nvidia/qdata
# 或：已在跑的 serve → export QAGENT_QDATA_URL=http://127.0.0.1:8787
PYTHONPATH=src python3 tests/test_a01_live.py
```

缺 flag、缺 home、URL 不通、CLI 失败：打印 skip，退出 0。不发明 `status=done`。不铸 `twin_id`。没有活输出里的 `asset_id` 就不许写「活 qdata 已通」。
