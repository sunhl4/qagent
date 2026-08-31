# A-03c · TwinRun ask / resume

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-26 |
| 角色 | S2 |
| 范围 | `qagent/src/qagent/adapters/ionstack.py` · `qagent/tests/test_a03c.py` |
| 未改 | `services/invoke.py` · `services/assignment.py` · `services/vibe_path.py` |

## 不变式

批准后续跑必须沿用待批 ask 里的同一 `circuit_id`，或同一 `circuit.body`。调用方改线路不得偷偷换 body。

`assignment._resume` 已经从 `row.ask.args` 原样绑定参数，不会重开黄金路径。本包在 `WiredIonstack.twin_run` 再加一道句柄核对：若带了已 pin 的 `circuit_id`，`circuit.body` 必须等于 pin 表里的 `logical`。对不上就抛 `ValueError`，`invoke` 记 `status=error`，**不**发 Twin REST，**不**写本地 `twin_id`。

只带 `circuit`、不带 `circuit_id` 的路径（E05 / 现有 approved 死 URL 测）仍允许；没有 pin 可对时不做假核对。

## 行为

| 条件 | 结果 |
|------|------|
| `ionstack_twin_run` 未批准 | `status=needs_ask`。不到端口。无 `twin_id` |
| `approved=True` 且 `QAGENT_TWIN_URL` 不通（测里用 `http://127.0.0.1:1`） | `status=error`。无 `twin_id`。文案写明未本地伪造 |
| 同一 `circuit_id` + 换成别的 `circuit.body` | 适配器抛错；`invoke` 为 `error`。无 `twin_id` |
| Twin `:8765` 活且 body 与 pin 一致 | 只有 REST 回了 `twin_id` + `counts` 才算成功 |

`:8765` 本波仍可能不通。不通就是诚实失败，不得本地铸造 `twin_id`。

## 测

```bash
cd qagent
PYTHONPATH=src python3 tests/test_a03c.py
PYTHONPATH=src python3 tests/run_tests.py
```

`test_a03c.py` 把 `QAGENT_TWIN_URL` 隔离到 `http://127.0.0.1:1`。E05 仍是活 Twin 或诚实错误；E19 Aer 无 `twin_id`。

## 剩

- 活 `:8765` 签收仍要人值守拉起 Twin。
- `tests/run_tests.py` / `PROGRESS.md` 留给调度挂测。
