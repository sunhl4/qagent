# O-01c · 对内 / 对外手册

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P |
| 范围 | `docs/handbooks/internal.md` · `docs/handbooks/customer.md` · `qagent/tests/test_o01c.py` |
| 状态 | 两本约 2 页已写，文本测绿 |

## 产品锁

- 组内本：脑是 `dsh --profile qagent`，脸是 3080。句柄只有 `circuit_id` / `asset_id` / `twin_id`。只有 TwinRun 发 `twin_id`。上机要问人，批准走同一 session。CAL / shuttle 不当工具。设置在组内，密钥不进对话。
- 对外本：用平常话交办，不必会 recipe 名。未签收不是绿封条。可拿走短回执，没有电路正文。不上别人的 IBM 冒充我们的机器。
- 两本都不发明第四个句柄。不加第三套 loop。不铸 `twin_id`。

## 不做什么

不改 `run_tests.py` / `PROGRESS.md` / customer-shell / `chat.py` / 任何 src 适配器 / `Q-*.json`。不 commit。`run_tests.py` / `PROGRESS.md` 留给调度挂。

## 测

```text
cd /Users/shl/nvidia/qagent && PYTHONPATH=src python3 tests/test_o01c.py
```
