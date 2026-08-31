# O-01p · 值班本写清 ELN 拒铸短 reason

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P |
| 范围 | `docs/handbooks/internal.md` · `docs/handbooks/customer.md` · `qagent/tests/test_o01p.py` |
| 状态 | 组内本写明拒铸行看得见短 reason。客户本最多一句。文本测绿 |

## 产品锁

- 组内可只读看实验记录。HTTP 是 GET，不要写 POST。可按交办过滤。拒铸行（claim_blocked）看得见短 reason（例如 Cirq 拒铸）。没有密钥、没有电路正文。
- 对外本最多一句：实验记录是组内的，客户脸不看实验流水。
- 保持组内本：`dsh --profile qagent`、3080、三句柄、TwinRun、CAL、shuttle、设置、组内、密钥。只读 GET，不要 POST，ELN / 实验记录。Cirq 已在软件包目录，`kind` 是互通，provenance 不是我们的机器。
- 手册正文只允许 `circuit_id` / `asset_id` / `twin_id`。过滤写「可按交办过滤」，不写其它句柄字段名。
- 不宣称过门。不加第三套 loop。不铸 `twin_id`。

## 不做什么

不改 `O-01c_handbooks.md` / `run_tests.py` / `PROGRESS.md` / customer-shell / `qagent/src` / `eln.md`。不 commit。`run_tests.py` / `PROGRESS.md` 留给调度挂。

## 测

```text
cd /Users/shl/nvidia/qagent && PYTHONPATH=src python3 tests/test_o01c.py
PYTHONPATH=src python3 tests/test_o01f.py
PYTHONPATH=src python3 tests/test_o01k.py
PYTHONPATH=src python3 tests/test_o01p.py
```
