# O-01h · start_ui 再打客户租户示例 URL

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P |
| 范围 | `qagent/scripts/start_ui.sh` · `qagent/tests/test_o01h.py` |
| 状态 | 客户脸后再打一行 `?tenant=` 示例（cust-a）。仍 loopback。**不算** G2 |

## 产品锁

- 保持 O-01e：`start_ui.sh` 仍写死 `--host 127.0.0.1`，打印 `http://127.0.0.1:…`。不加 `0.0.0.0`。先打 token 行，再打客户脸 `?token=${QAGENT_SHELL_TOKEN}&role=customer`。
- 客户脸那一行之后再 echo 一行客户租户示例：同一 loopback、同一 `QAGENT_SHELL_TOKEN`、`role=customer`，地址写 `?tenant=`（例如 cust-a）。不写第四个句柄字段名。
- 这仍不是 G2 过门。不宣称过门。不铸 `twin_id`。不加第三套 loop。
- 句柄只有 `circuit_id` / `asset_id` / `twin_id`。不发明第四个。

## 不做什么

不改 `O-01e_start_ui_customer.md` / `run_tests.py` / `PROGRESS.md` / customer-shell / `qagent/src`。不 commit。`run_tests.py` / `PROGRESS.md` 留给调度挂。

## 测

```text
cd /Users/shl/nvidia/qagent && PYTHONPATH=src python3 tests/test_o01e.py
PYTHONPATH=src python3 tests/test_o01h.py
```
