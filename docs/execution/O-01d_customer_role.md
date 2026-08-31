# O-01d · 客户手册写明 `?role=customer`

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P |
| 范围 | `docs/handbooks/customer.md` · `qagent/tests/test_o01d.py` |
| 状态 | 对外本补了客户角色入口，文本测绿。O-01c 仍绿 |

## 产品锁

- 客户打开 3080 用 `?role=customer`，可与 `?token=` 写在一起。壳侧（C-01d）已落地：写入后从地址栏拿掉。本包只写对外本，不改 customer-shell。
- 进客户角色后，设置里看不到密钥值，密钥栏会藏。这是用法说明，不是再开一套程序。
- 这仍不是 G2 过门。不宣称过门。交办仍是平常话，签收仍看绿封条。
- 句柄只有 `circuit_id` / `asset_id` / `twin_id`。不发明第四个。不铸 `twin_id`。不加第三套 loop。

## 不做什么

不改 `docs/handbooks/internal.md` / `run_tests.py` / `PROGRESS.md` / `test_o01c.py` / customer-shell / `qagent/src` / `chat.py`。不 commit。`run_tests.py` / `PROGRESS.md` 留给调度挂。

## 测

```text
cd /Users/shl/nvidia/qagent && PYTHONPATH=src python3 tests/test_o01d.py
cd /Users/shl/nvidia/qagent && PYTHONPATH=src python3 tests/test_o01c.py
```
