# C-01g · 3080 欢迎列表也画引擎 kind

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P |
| 范围 | `qagent/apps/customer-shell/*` · `qagent/tests/test_c01g.py` |
| 状态 | 代码落地，文本测绿。不算过门。 |

## 产品锁

- 欢迎页 `.packs` 每行与设置 `#engine-list` 一样带上 `kind`：`label · kind · status`（例如 `Cirq 互通 · interop · wired`）。用 `textContent` 写行，不要 `innerHTML` 拼包名。
- 组内看见 Cirq 是 interop，不是我们的机器。Cirq 不许发 `twin_id`。句柄仍只有 `circuit_id` / `asset_id` / `twin_id`。
- 不做模型墙。没有三房间、Finder、`btn-twin`。HTML 正文不写 `assignment_id`。
- 保持 C-01e：未就绪 `showModal`；对话 `open_settings` 且仍未就绪可再开；已签收回执下载 / 核验；`?role=customer` 仍藏 `#secret-fieldset`；IME / `aria-busy` 不动。
- 保持 I-03e：`GET /api/eln` 只读、无 POST。
- 保持 C-02d：`?tenant=` → `X-QAGENT-TENANT`；空租户不带头。

## 不做什么

不改 `qagent/src/**`（`list_engines` 已回 `kind`）。不改 `run_tests.py` / `PROGRESS.md` / `G1_demo.md` / handbooks。不加第三套 agent loop。不编造 `twin_id`。不 commit。本包只让欢迎列表与设置同画 `kind`，**不算** G0 / G2 过门。

## 测

`qagent/tests/test_c01g.py`：欢迎 `.packs` 与 `#engine-list` 同式 `label · kind · status`；`textContent` 写包名；不宣称过门；无三房间 / Finder；`GET /api/eln` 只读；C-01e 设置 / 回执句子仍在；`?tenant=` 仍带头。

```text
PYTHONPATH=src python3 tests/test_c01g.py
PYTHONPATH=src python3 tests/test_c01e.py
PYTHONPATH=src python3 tests/test_i03e.py
PYTHONPATH=src python3 tests/test_c02d.py
```
