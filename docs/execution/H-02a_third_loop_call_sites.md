# H-02a · 第三 loop 调用点清单

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-26 |
| 角色 | A2 |
| 范围 | `qagent/src` + `qagent/tests`（不含 `node_modules`） |
| 规则 | H-01 未过，禁止扩 `agent.py` |

## 产品循环（必须离开 `/api/chat`）

| 符号 | 文件 | 谁调用 |
|------|------|--------|
| `def _loop` | `qagent/src/qagent/services/agent.py` | `turn()`、`_resume_ask()` |
| `turn()` | 同上 | 本清单「入口」 |
| `OpenAICompatClient` | `qagent/src/qagent/adapters/llm.py` | `agent._default_client()`；`turn(..., client=)` 可注入 |
| `agent.turn` | `qagent/src/qagent/services/agent.py` | 见下 |

## 入口（2026-08-26 探活时）

| 文件 | 用法 | 处置 |
|------|------|------|
| `services/agent.py` | 定义 `classify` / `turn` / `_loop` / `reset_agent` | 本周不扩。H-02b 标 deprecated 或删 `_loop` |
| `services/chat.py` | **曾** `from agent import classify, turn` | **本会话已改**：产品 `turn` 走 `DshSessionClient` |
| `entrypoints/shell_http.py` | `POST /api/chat` → `turn`；`POST /api/agent/reset` | **本会话已改**：import `qagent.services.chat` |
| `tests/run_tests.py` `test_chat` | 仍直接 `agent.turn(..., client=Scripted)` | 保留为「旧 loop 单元」直到 H-02b；`/api/chat` 不再走它 |

`adapters/qdata.py` 命中的 `_loop` 是 recipe 名 `a1_closed_loop`，**不是** agent loop。

## 允许留下的（不是第三 loop）

| 符号 | 为什么可以 |
|------|------------|
| `classify()` | 只认「批准 / 拒绝 / 空」，给 HTTP 门闩用 |
| `invoke()` / `decide()` | 科学合同，dsh 插件也转调它们 |
| `OpenAICompatClient` 文件 | H-03 模型池可能还要测连通；**禁止**再被 `/api/chat` 当 harness |

## H-02b 验收预告

```text
rg "def _loop" qagent/src     # 可以还在
# 但 tests 里 POST /api/chat 的调用栈不得进入 services.agent._loop
```

`agent-thread.json` 不再是产品对话真源。产品 session id 在 `.qagent/dsh-session.json`（`QAGENT_DSH_SESSION_FILE`）。
