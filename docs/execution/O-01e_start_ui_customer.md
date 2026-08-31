# O-01e · start_ui 打印客户脸 URL

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P |
| 范围 | `qagent/scripts/start_ui.sh` · `qagent/tests/test_o01e.py` |
| 状态 | 第二行客户脸 `?token=` 且 `role=customer`。仍 loopback。**不算** G2 |

## 产品锁

- `start_ui.sh` 仍写死 `--host 127.0.0.1`，打印 `http://127.0.0.1:…`。不加 `0.0.0.0`。
- 原 token 行保留。其后多打一行客户脸：同一 `QAGENT_SHELL_TOKEN`，地址为 `?token=…&role=customer`，标成「客户脸」。
- 这仍不是 G2 过门。不宣称过门。不铸 `twin_id`。不加第三套 loop。
- 句柄只有 `circuit_id` / `asset_id` / `twin_id`。不发明第四个。

## 不做什么

不改 `run_tests.py` / `PROGRESS.md` / `test_o01b.py` / `test_o01c.py` / customer-shell / `qagent/src`。不 commit。`run_tests.py` / `PROGRESS.md` 留给调度挂。

## 测

```text
cd /Users/shl/nvidia/qagent && PYTHONPATH=src python3 tests/test_o01e.py
cd /Users/shl/nvidia/qagent && PYTHONPATH=src python3 tests/test_o01b.py
```
