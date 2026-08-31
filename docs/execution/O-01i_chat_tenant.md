# O-01i · 手册写已设租户各一条对话

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P |
| 范围 | `docs/handbooks/internal.md` · `docs/handbooks/customer.md` · `qagent/tests/test_o01i.py` |
| 状态 | 组内本写明已设租户各一条对话；空租户仍是组内那条。客户本最多一句。文本测绿 |

## 产品锁

- 已设租户各走各的对话，不共用一条 session。空租户仍是组内那条。
- 对外本最多一句：两位客户不要看见对方正在说的话。
- 保持组内本：只读 GET、ELN / 实验记录、`open_settings`、可按交办过滤。空租户见全部；客户脸用 `?tenant=`，请求头带租户。空租户不要带头。
- 手册正文只允许 `circuit_id` / `asset_id` / `twin_id`。对话写「对话」或 session。不写其它句柄字段名。
- 不宣称过门。不加第三套 loop。不铸 `twin_id`。

## 不做什么

不改 `O-01c_handbooks.md` / `O-01g_tenant_handbook.md` / `run_tests.py` / `PROGRESS.md` / customer-shell / `qagent/src`。不 commit。`run_tests.py` / `PROGRESS.md` 留给调度挂。

## 测

```text
cd /Users/shl/nvidia/qagent && PYTHONPATH=src python3 tests/test_o01c.py
PYTHONPATH=src python3 tests/test_o01f.py
PYTHONPATH=src python3 tests/test_o01g.py
PYTHONPATH=src python3 tests/test_o01i.py
```
