# A-02-live · 活 qchem 诚实记录

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | S2 · A-02-live |
| 范围 | 只本笔记 + `qagent/tests/test_a02_live.py` |
| 未改 | `qagent/src/**`（适配器已 fail-close）· `test_a02.py` · `run_tests.py` · `PROGRESS.md` · customer-shell · chat / dsh / qdata adapters |
| 状态 | 活 `qchem-run minimal_vqe` **未打**。活 qchem **未证明**（unproven） |

## 产品锁

- 活 `qchem-run --scenario minimal_vqe --json-summary` **未证明**，除非本笔记抄到一次真实 bin 输出，且里面有 `asset_id`（真 CLI 的 `json-summary` 只印 `experiment_id` 时，只把该字段记成 `asset_id`；不许另铸）。
- 缺 bin / 死 bin 已由 [A-02](A-02_qchem_honesty.md) 覆盖：无 HOME 走本地卡 `qagent-local-card`；死路径不冒充 `qchem-cli`。本包不重写那条失败，不改口。
- 不铸 `twin_id`。无 twin_id。电路体 / QASM / `circuit_id` 不当句柄。句柄只有 `circuit_id` / `asset_id` / `twin_id`，本包只许出 `asset_id`。
- **不发明** `qchem-cli` 成功。`test_a02.py` 的临时假脚本不是活 CLI。本地卡出的 `asset_id` 不是活 qchem。
- 默认测例只读本笔记。活探函数存在，但除非 `QAGENT_LIVE_QCHEM=1` **且** bin 真通并打回 `asset_id`，否则不调用。

## 活 `asset_id` 规则

活 qchem **未证明**（unproven）。没有真实命令输出就写「活 qchem 已通」是造假。`--help`、`--list-scenarios`、checkout 在场、假 CLI、本地卡、死 bin 抛错，都不是活通。

## 2026-08-27 本轮记录

`QAGENT_LIVE_QCHEM` **未设**。按合同 **未打** `qchem-run --scenario minimal_vqe --json-summary`。**未写** `source=qchem-cli`。**不许**说「活 qchem 已通」。

| 检查 | 结果 |
|------|------|
| `QAGENT_LIVE_QCHEM` | **未设** |
| `QAGENT_QCHEM_HOME` | **未设** |
| `QAGENT_QCHEM_BIN` | **未设** |
| `QAGENT_QCHEM_PARITY_BIN` | **未设** |
| PATH `qchem-run` | **无**（`qchem-run not found`） |
| checkout `/Users/shl/nvidia/qcchem-qml-md` | **在**。`.venv/bin/qchem-run` 可执行（202 B，2026-06-15）。本轮未 export HOME，不算已通 |
| `qchem-run --help` | 有 `--scenario` / `--json-summary`。这是 help，**不是** `minimal_vqe` |
| `--list-scenarios` | 目录里有 `minimal_vqe`。这是清单，**不是** 活跑 |
| `qchem-run --scenario minimal_vqe --json-summary` | **未打** |
| 活 `asset_id` | **无** |
| `source=qchem-cli` | **未写** |
| `twin_id` | **无**。不铸 |
| 电路体当句柄 | **无** |

`--help` 原文（不是 `minimal_vqe`，没有 `asset_id`）：

```
usage: qchem-run [-h] [--list-scenarios] [--scenario ID] [--set KEY=VAL]
                 [--job-db JOB_DB] [--json-summary]
                 [config]
```

`--json-summary` 帮助句（能量字段，不是句柄）：

```
--json-summary    Print a small JSON summary (scf_energy, variational,
                    pauli) to stdout
```

本轮没有活 `asset_id`，所以活 qchem **未证明**。缺 CLI / 死 bin 的诚实失败仍归 A-02（无 HOME 本地卡；死路径不冒充 qchem-cli）。

## 未做

- 不改 `qchem.py` / `homes.py` / `qdata` adapters / `run_tests.py` / `PROGRESS.md` / `test_a02.py` / customer-shell / `chat.py` / `dsh_session.py`。
- 不把 checkout 在场、`--help`、或 `--list-scenarios` 写成已通。
- 不把 `test_a02.py` 临时假脚本当成活 CLI。
- 不调 `ionstack_twin_run`。不发明第四句柄。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_a02.py
PYTHONPATH=src python3 tests/test_a02_live.py
```

活探（可选，且 HOME 或 BIN 必须真通）：

```bash
cd /Users/shl/nvidia/qagent
export QAGENT_LIVE_QCHEM=1
export QAGENT_QCHEM_HOME=/Users/shl/nvidia/qcchem-qml-md
# 或：export QAGENT_QCHEM_BIN=/Users/shl/nvidia/qcchem-qml-md/.venv/bin/qchem-run
PYTHONPATH=src python3 tests/test_a02_live.py
```

缺 flag、缺 home、死 bin、CLI 失败：打印 skip，退出 0。不发明 `qchem-cli`。不铸 `twin_id`。没有活输出里的 `asset_id` 就不许写「活 qchem 已通」。
