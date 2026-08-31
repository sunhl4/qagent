# Qagent 橙皮书（开机清单）

官方 dsh 文档没有的组内实测入口。不自研 loop。脑仍是 `dsh --profile qagent`。

## Read First

1. `qagent/AGENTS.md`
2. `qagent/contracts/`（政策、preset、评测）
3. `qagent/INTERFACES.md`
4. 本页

## 启动清单

1. `cd qagent && PYTHONPATH=src python tests/run_tests.py`
2. `PYTHONPATH=src python -m qagent.entrypoints.eval_cli`
3. `PYTHONPATH=src python -m qagent.entrypoints.doctor_cli`
4. 人入口：`bash scripts/start_ui.sh` → `http://127.0.0.1:3080`
5. 写算法再开 runtime：`bash scripts/start_runtime.sh` → `:3081`
6. 两阶段：先 `dsh --profile qagent-minimal` + `boot`，再切 `qagent` + `lab`
7. 凭证只进 ignored `.qagent/secrets.json` / `.env`。Agent 只验证非空与行为，不读值。
8. 上机：`ionstack_twin_run` 必须 `needs_ask`。没有批准不要跑。
9. Aer / Cirq / 本地卡出现 `qccd-twin` 或 `twin_id` → doctor 红。
10. `quantum_wins` 没有 `qem_contract_ok` → 后验 error。
11. 3080↔3081 交接走 `qagent-gov handoff`，只带三个句柄。
12. 崩溃：`qagent-gov savepoint` 后 `qagent-gov safe-mode` 回到 boot。
13. 生产不挂 `cordis_define` / `dangerously-bypass` / 通用出网 MCP。
14. 镜像只跑 3080 shell，不把 ionstack 打进去。
15. 槽位号不是原因。查 `handbooks/errors.md` 或 `GET /api/errors`。孪生灯亮不等于预估可用。
16. `list_engines` 不带 preset 只读；带 preset 会切会话。

## 任务路由

| 任务 | 先做什么 | 停下来的条件 |
|------|----------|----------------|
| 造包 | `boot` / `qagent-minimal`；只 pin 与手册 | 任何 Twin 工具出现在可见集 |
| 评测 | `qagent-eval` E01–E21 与 E28–E32 | 断言失败；不要改工具名去凑绿 |
| 上机 | 查 `GET /api/asks` 与许可单 | 未批准、无活 Twin、provenance 不诚实 |

## 句柄

只有 `circuit_id` / `asset_id` / `twin_id`。第三项只由 ionstack TwinRun 签发。
