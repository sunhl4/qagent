# O-01q · 值班本写清 Pennylane 已 reserved、不在目录

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P |
| 范围 | `docs/handbooks/internal.md` · `docs/handbooks/customer.md` · `qagent/tests/test_o01q.py` |
| 状态 | 组内本写明 Pennylane 已 reserved、不在目录、不在软件包目录 / `engines[]`。保持 Cirq 已在目录且互通。客户本不写 Pennylane。文本测绿 |

## 产品锁

- Cirq 已在软件包目录。`kind` 是互通。provenance 不是我们的机器。保持 o01k。
- Pennylane 已 reserved，不在目录，也不在软件包目录 / `engines[]`。再加真机仍按加包说明。加包不是加句柄。
- 对外本不写 Pennylane / reserved_engines。最多保持：别人的模拟器不是我们的机器签收。
- 保持组内本：`dsh --profile qagent`、3080、三句柄、TwinRun、CAL、shuttle、设置、组内、密钥。只读 GET，不要 POST，ELN / 实验记录，claim_blocked 短 reason（例如 Cirq 拒铸）。
- 手册正文只允许 `circuit_id` / `asset_id` / `twin_id`。不写其它句柄字段名。
- 不宣称过门。不加第三套 loop。不铸 `twin_id`。不算接线 Pennylane。不要把 Cirq 放回 reserved。

## 不做什么

不改 `O-01c_handbooks.md` / `run_tests.py` / `PROGRESS.md` / customer-shell / `qagent/src`。不 commit。`run_tests.py` / `PROGRESS.md` 留给调度挂。

## 测

```text
cd /Users/shl/nvidia/qagent && PYTHONPATH=src python3 tests/test_o01k.py
PYTHONPATH=src python3 tests/test_o01c.py
PYTHONPATH=src python3 tests/test_o01p.py
PYTHONPATH=src python3 tests/test_o01q.py
```
