# C-02d · 3080 客户脸带上租户头

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P |
| 范围 | `qagent/apps/customer-shell/*` · `qagent/tests/test_c02d.py` |
| 状态 | 代码落地，文本测绿。不算过门。 |

## 产品锁

- `?tenant=` 与 `?role=customer` / `?token=` 同一段：写入 localStorage 键 `QAGENT_SHELL_TENANT`，再 `history.replaceState` 清掉 query。
- `headers()` 有租户值才带 `X-QAGENT-TENANT`。空租户不带头，组内仍见全部（与 C-02 一致）。
- 租户不是句柄。句柄只有 `circuit_id` / `asset_id` / `twin_id`。
- 不做模型墙、不做租户下拉当主操作。没有三房间、Finder、`btn-twin`。HTML 正文不写 `assignment_id`。
- 保持 I-03e：`GET /api/eln` 只读、无 POST；回执下 ELN 区块；`textContent`；不画密钥 / body / qasm3。
- 保持 C-01e：未就绪 `showModal`；对话 `open_settings` 且仍未就绪可再开；已签收回执下载 / 核验；`?role=customer` 仍藏 `#secret-fieldset`；IME / `aria-busy` 不动。
- 就绪时健康行可读公开 `next_model`，仍保留 `llm_model`。不画密钥。

## 不做什么

不改 `qagent/src/**`（头已是 `X-QAGENT-TENANT` / `x-qagent-tenant`）。不改 `chat.py` / `eln.py` / `run_tests.py` / `PROGRESS.md` / `PARALLEL.md` / `G2_demo.md` / handbooks。不加第三套 agent loop。不编造 `twin_id`。不 commit。本包只补 3080 脸带头，**不算** G0 / G2 过门。

## 测

`qagent/tests/test_c02d.py`：js 有 `?tenant=`、`X-QAGENT-TENANT`、`QAGENT_SHELL_TENANT`；空租户不强制带头；不宣称过门；无三房间 / Finder；`GET /api/eln` 只读；C-01e 设置 / 回执句子仍在。

```text
PYTHONPATH=src python3 tests/test_c02d.py
PYTHONPATH=src python3 tests/test_c01e.py
PYTHONPATH=src python3 tests/test_c01d.py
PYTHONPATH=src python3 tests/test_i03e.py
PYTHONPATH=src python3 tests/test_i01c.py
PYTHONPATH=src python3 tests/test_r03c.py
```
