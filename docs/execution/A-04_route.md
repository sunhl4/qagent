# A-04 · route 合同

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-26 |
| 角色 | S2 |
| 范围 | `qagent/src/qagent/adapters/route.py` · `qagent/tests/test_a04.py` |
| 未改 | `ionstack.py`（只读：`QAGENT_ROUTE_BACKEND` 选 `alt_estimate` / `mapqccd_estimate`） |

## 行为

| 条件 | 结果 |
|------|------|
| `mapqccd_estimate` / `alt_estimate` | 必有 `makespan_ns`。顶层和 `summary` 都没有 `ok` / `twin_id` / `signoff` / `signed` / `signature` |
| `QAGENT_ROUTE_BACKEND` 未设或 `mapqccd` | `summary.backend=mapqccd`。工具名仍是 `ionstack_compile_estimate` |
| `QAGENT_ROUTE_BACKEND=route-alt` | `summary.backend=route-alt`，makespan 公式不同。工具名仍是 `ionstack_compile_estimate` |
| `WiredRoute.compile_estimate` | 读同一环境变量换实现，不注册第二工具名 |

`invoke("ionstack_compile_estimate", …)` 仍走 ionstack 端口；route 只提供两套估计实现。不发 `twin_id`。

## 测

```bash
cd qagent
PYTHONPATH=src python3 tests/test_a04.py
PYTHONPATH=src python3 tests/run_tests.py
```

环境在 `test_a04.py` 里隔离 `QAGENT_ROUTE_BACKEND`。E12 / E14 在本包测和 `run_tests.py` 里都跑。

## 剩

- 活 MapQccd interop 仍由 ionstack 端口决定是否调用；本包只保证合同估计函数干净。
- `tests/run_tests.py` / `PROGRESS.md` 留给调度挂测。
