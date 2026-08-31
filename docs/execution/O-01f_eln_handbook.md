# O-01f · 组内/客户手册补 ELN 只读与未就绪开设置

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P |
| 范围 | `docs/handbooks/internal.md` · `docs/handbooks/customer.md` · `qagent/tests/test_o01f.py` |
| 状态 | 组内本写明 ELN 只读 GET；未就绪开设置。客户本最多一句。文本测绿 |

## 产品锁

- 组内可只读看实验记录。HTTP 是 GET，不要写 POST。可按交办过滤。没有密钥、没有电路正文。
- 未就绪时 3080 打开设置（`open_settings` / 设置对话框）。仍是同一张脸，不是第三套 loop。
- 客户面不看组内实验流水、不看密钥。客户本不写成能追加 ELN。
- 手册正文只允许 `circuit_id` / `asset_id` / `twin_id`。过滤写「可按交办过滤」，不写其它句柄字段名。
- 不宣称过门。不加第三套 loop。不铸 `twin_id`。

## 不做什么

不改 `O-01c_handbooks.md` / `run_tests.py` / `PROGRESS.md` / customer-shell / `qagent/src`。不 commit。`run_tests.py` / `PROGRESS.md` 留给调度挂。

## 测

```text
cd /Users/shl/nvidia/qagent && PYTHONPATH=src python3 tests/test_o01c.py
PYTHONPATH=src python3 tests/test_o01d.py
PYTHONPATH=src python3 tests/test_o01e.py
PYTHONPATH=src python3 tests/test_o01f.py
```
