# H-02f · agent.turn 拒绝当产品

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P / H-02f |
| 范围 | `qagent/src/qagent/services/agent.py` · `qagent/tests/test_h02f.py` · 本笔记 |
| 状态 | 代码落地，测绿 |

## 产品锁

- `agent.turn` 一调用就抛 `RuntimeError`。文案指向 `services.chat.turn`，并写明 **turn 不是产品循环**。
- 不进 `_loop`，不调模型。`def _loop` 仍留在源码（计划允许文件里还在）。
- `reset_agent()` 仍可直接调。`run_tests.py` company_shell 继续用它。
- `shell_http.py` 仍无 `services.agent` / `reset_agent`。
- 不算接线。不宣称 G0/G2。句柄仍只三个：`circuit_id` / `asset_id` / `twin_id`。

## 不做什么

不改 `services/chat.py` / `shell_http.py` / `run_tests.py`。不删 `_loop`。不接线 Pennylane。不加第四句柄。不铸 `twin_id`。不扩第三套 loop。不 commit。`PROGRESS.md` / `PARALLEL.md` 留给调度挂。
