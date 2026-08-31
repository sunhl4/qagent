# H-03i · 脸 HOME health

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | A1 · H-03i |
| 范围 | 只本笔记 + `qagent/tests/test_h03i.py` |
| 未改 | `qagent/src/**` · `start_ui.sh` · `test_h03h.py` · `workplace.json` · `dsh.env` · `secrets.json` · `run_tests.py` · `PROGRESS.md` · `PARALLEL.md` |
| 状态 | 3080 `GET /api/health` 四条 true。`GET /api/workplace` 表单已 ready（地址 + 模型名）。`has_llm_key` 仍是 false。**不算接线**。**不算 G0**。 |

H-03h 让 `start_ui.sh` 在四个 HOME 为空时从 `dsh.env` 再从 `workplace.json` 补 export。本包不改启动脚本，只打已在跑的 3080 脸，抄活 health。`science_health()` 里 `qchem_live` 看 `qchem_bin()`，`qdata_cli` 看 `qdata_bin()`；脸进程看见 HOME 之后这两位才能是 true。

不铸 `twin_id`。只有 `circuit_id` / `asset_id` / `twin_id`。无第四句柄。不调 TwinRun。不接线 Pennylane。不读 `secrets.json`。不写密钥。

## 诚实

这是 **脸 HOME health**：3080 进程已经看见三条 HOME，health 里 `qchem_live` / `qdata_cli` 为 true。**不算接线**。不算活 A-01。**不算 G0**。人已填地址和模型名，表单已 ready；钥匙仍不在 GET 里。

**skip 当绿 = 没做完**。3080 不通必须失败。

## 2026-08-27 真实 health JSON

测打的就是这一条，token 只用于 query，不是密钥：

```http
GET http://127.0.0.1:3080/api/health?token=workbench-review
```

抄到的原文：

```json
{"twin_live": true, "qdata_live": true, "qchem_live": true, "qdata_cli": true, "runtime_url": "http://127.0.0.1:3081"}
```

| 字段 | 值 |
|------|-----|
| twin_live | true |
| qdata_live | true |
| qchem_live | true |
| qdata_cli | true |
| runtime_url | `http://127.0.0.1:3081` |

`GET http://127.0.0.1:3080/api/workplace?token=workbench-review`：**200**。顶层表单已 ready。`workplace.has_llm_key` / `has_hpc_secret` / `has_quantum_secret` 都是 false。`llm_model=deepseek-v4-flash`，`llm_base_url=https://api.deepseek.com/v1`。JSON **没有** `llm_api_key` / `hpc_secret` / `quantum_secret` 键，**没有密钥值**。公开 HOME（不是密钥）：`qdata_home=/Users/shl/nvidia/qdata`，`qchem_home=/Users/shl/nvidia/qcchem-qml-md`，`ionstack_home=/Users/shl/Q-software`。`knowledge_path` 空。未抄 `engines[]`。

## 不算什么

- **不算 G0**。表单已 ready 不是过门。人还没走完「扫氢分子」三步。
- **不算 G2**。没有客户面回执演示。
- 不算接线 Pennylane。Pennylane 仍只 reserved。
- 不算改了 `start_ui.sh` / `health.py`。那是 H-03h 与既有探针。
- **未 commit**。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_h03i.py
PYTHONPATH=src python3 tests/run_tests.py
```

- `GET /api/health`：`qchem_live is True`、`qdata_cli is True`。`twin_live` / `qdata_live` 保持 True。
- `GET /api/workplace`：表单已 ready；`has_llm_key` 仍是 False。
- 3080 不通必须失败。skip 当绿 = 没做完。不 commit。

## 不做

- 不改 `qagent/src/**` / `start_ui.sh` / `test_h03h.py` / `workplace.json` / `dsh.env` / `secrets.json`。
- 不 commit。`run_tests.py` / `PROGRESS.md` / `PARALLEL.md` 留给调度。
- 不宣称过门。不重启 dsh。不 pkill dsh。
