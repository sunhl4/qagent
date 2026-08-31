# Qagent 填坑宪法

合同在 `contracts/`。实现在 `src/qagent/adapters/`。评测在 `contracts/eval/`。dsh 插件只转调 `invoke()`。

## Read First

1. 本页
2. `INTERFACES.md`
3. `handbooks/orange-book.md`
4. `contracts/policy.json` 与 `contracts/presets.json`

## 任务路由

| 任务 | 路径 | 第一步 |
|------|------|--------|
| 造包 | `qagent-minimal` + `boot` | 确认 Twin 插件不在产物里 |
| 评测 | `python -m qagent.entrypoints.eval_cli` | 断言字段，不改工具名 |
| 上机 | `lab`/`sign` + ask | 先看许可单 / `GET /api/asks` 与健康四灯，未批则停 |
| 排错 | `GET /api/errors` + `handbooks/errors.md` | 不要把 S-TWIN-03 当原因 |

## 硬规则

1. **禁止 import** `qdata` / `ionstack` / `qchem` / `qiskit`。围栏在 `services/boundaries.py`。接线用 REST / CLI / 合同 store。
2. **不改工具名。** 改 schema 必须同时改评测与政策行。
3. **不自研 loop。** 插件只 `apply(ctx)` 注册工具 / 政策 / 事件。
4. **失败闭合。** 政策抛错 = deny。没有规则 = deny。
5. **短输出。** 工具返回 id + summary + 字段。禁止 bitstrings / Pauli 全文 / CAL。
6. **上机不进官方 Codex never。** `ionstack_twin_run` 只活在 dsh 合同工具 + ask。
7. **B3/QEM 是字段。** 未过不得写 `quantum_wins`。
8. **Aer 不得复制签收 `twin_id`。**
9. 生产不挂 `cordis_define` / `dangerously-bypass` / 通用出网 MCP。

## 层

- `contracts/` — 真源
- `src/qagent/models/` — 句柄、Protocol、政策枚举
- `src/qagent/adapters/` — 已接线端口
- `src/qagent/services/` — `decide` / `invoke` / 围栏 / eval
- `packages/` — dsh 插件，`execute` 只调 `invoke()`
- `profiles/` — 组合，不写逻辑。`qagent-minimal` 是第一阶段（无 Twin 插件）。
- `contracts/handoff/` — 3080↔3081 固定 schema，只带三个句柄。
