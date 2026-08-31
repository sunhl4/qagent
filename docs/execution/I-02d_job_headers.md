# I-02d · 远程作业 HTTP 带 Bearer，loopback 不带

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P · I-02d |
| 范围 | `qagent/src/qagent/adapters/support.py` · `qdata.py` 列表 GET · `workplace.py` `probe_cloud` · 本笔记 · `qagent/tests/test_i02d.py` |
| 未改 | `chat.py` · `agent.py` · `assignment.py` · `run_tests.py` · `PROGRESS.md` · ionstack 核 |
| 状态 | 非 loopback URL 才把 `hpc_secret`/`quantum_secret` 写成 `Authorization: Bearer`。本机 Twin / qdata 不带。状态 JSON 仍无密钥。**不算 G0**。未 commit。 |

## 产品锁

- I-02b：适配器只读凭据，提交 job 用，不进模型上下文。头函数原先在，南向 HTTP 没用。
- 完成线：`json_headers(url)`。`127.0.0.1` / `localhost` / `::1` 不加 Bearer。远程才加。
- GET `/api/workplace` 与 dsh prompt 仍无密钥值。
- 活 Twin `:8765` / qdata `:8787` 仍不带作业头。
- **不算 G0**。没有填模型。skip 当绿 = 没做完。未 commit。

## 2026-08-27 真实脸

隔离夹具：`https://hpc.example/v1/jobs` 有 Bearer。`http://127.0.0.1:8765/...` 无 Authorization。活 Twin identity 仍通。

## 不算什么

- **不算 G0**。ready 仍 false。
- 未把 CAL 塞进工具。未假 `twin_id`。未 commit。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_i02d.py
PYTHONPATH=src python3 tests/test_i02.py
PYTHONPATH=src python3 tests/run_tests.py
```

loopback 被带上 Bearer 必须失败。skip 当绿 = 没做完。不 commit。
