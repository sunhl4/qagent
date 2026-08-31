# C-01d · 客户角色不见密钥值

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P |
| 范围 | `qagent/apps/customer-shell/*` · `qagent/tests/test_c01d.py` |
| 状态 | 代码落地，文本测绿 |

## 产品锁

- 客户角色走 URL `?role=customer`，和 `?token=` 一样写入 localStorage 后从地址栏拿掉。
- `#secret-fieldset` 在客户角色下 `hidden` + `aria-hidden`。`#hpc_secret` / `#llm_api_key` / `#quantum_secret` 仍留在 DOM，type=password，给员工设置用。
- `fillSettings` 只把非密钥 workplace 字段写进输入框。三枚密钥一律 `el.value = ""`，placeholder「已保存」。不从 status / workplace JSON 回填值。
- 3080 仍是对话主面。不加 Finder 工作区，不加三房间，不加 `btn-twin`。

## 不做什么

不改 `qagent/src/**`（GET /api/workplace 已是 `has_*`）。不改 `chat.py` / `dsh_session.py`。不加第三套 agent loop。不编造 `twin_id`。不 commit。`run_tests.py` / `PROGRESS.md` 留给调度挂。本包不是 G2 过门声明。
