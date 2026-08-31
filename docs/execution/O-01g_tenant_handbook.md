# O-01g · 手册写 3080 租户怎么带

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P |
| 范围 | `docs/handbooks/internal.md` · `docs/handbooks/customer.md` · `qagent/tests/test_o01g.py` |
| 状态 | 组内本写明空租户见全部；客户脸用 `?tenant=` 带头。文本测绿 |

## 产品锁

- 组内空租户看见全部交办和实验记录。空租户不要带头。
- 客户脸用 `?tenant=`，请求头带租户。仍是同一张脸，不是第三套 loop。
- 对外本最多一两句：两位客户各走各的，不要看见对方的在办和回执。地址栏写 `?tenant=`。
- 手册正文只允许 `circuit_id` / `asset_id` / `twin_id`。不写其它句柄字段名。
- 保持组内本：只读 GET、`open_settings`、可按交办过滤。客户不看实验流水。
- 不宣称过门。不加第三套 loop。不铸 `twin_id`。

## 不做什么

不改 `O-01c_handbooks.md` / `O-01f_eln_handbook.md` / `run_tests.py` / `PROGRESS.md` / customer-shell / `qagent/src`。不 commit。`run_tests.py` / `PROGRESS.md` 留给调度挂。

## 测

```text
cd /Users/shl/nvidia/qagent && PYTHONPATH=src python3 tests/test_o01c.py
PYTHONPATH=src python3 tests/test_o01d.py
PYTHONPATH=src python3 tests/test_o01f.py
PYTHONPATH=src python3 tests/test_o01g.py
```
