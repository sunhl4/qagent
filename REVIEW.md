# 骨架审查（先于填坑）

对照 2026-08-21 源码，不是对照愿望。空壳按这些事实开槽；填的时候不要改合同名。

## 引擎侧（已存在，不要重写）

| 事实 | 路径 | 骨架怎么接 |
|------|------|------------|
| qdata 五工具 MCP 已能跑，但**不能当生产合同** | `/Users/shl/nvidia/qdata/packages/qdata-serve/src/qdata/serve/mcp_server.py` | `S-QDATA-*` 先冻硬化后的 schema，adapter 填实现 |
| `main()` 默认 `mkdtemp`，下次会话资产蒸发 | 同文件 `McpServer()` | `S-QDATA-01`；E02 断言临时目录失败 |
| `get_job` 回整个 job 对象 | `call()` 里 `return j` | `S-QDATA-03`；输出只许 `status` + `summary` + `asset_id` |
| `run_recipe` 任意 `importlib.import_module` | 无 allowlist | `S-QDATA-02`；政策 `R-RECIPE-UNKNOWN` 已写成 deny |
| 无 `get_run_record` / `dequant_gate` | 工具表只有 5 个 | `S-QDATA-05/06`；B3 `verdict` 枚举已冻 |
| 冻结配方名 | `qdata_recipes/__init__.py` | allowlist：`a1_closed_loop` `a2_spin_shadow` `a2_chem_pes` `a3_sensitivity` `qem_triad` |
| qchem-stack 零 MCP，CLI 是 `qchem-run` | `/Users/shl/nvidia/qcchem-qml-md` | `S-QCHEM-*` P1；不要 P0 假装已接 |
| TwinRun REST 已 GA | `GET /v1/twin/identity` `POST /v1/twin/run` | `S-TWIN-*`；请求体必填 `mode` / `shots` / `circuit.body`（ionstack `TwinRunRequest`） |
| 机器身份在服务端 | `IONSTACK_TWIN_PRESET` 等 | 工具**不得**收 CAL / shuttle |
| `compile_estimate` 北向未包 | MapQccd 在 ionstack 内 | 同一工具名；结果有 `makespan_ns`，**无**签收 `ok` |
| Qiskit 互通已在 ionstack | `ionstack/interop/qiskit_*.py`、`aer_bridge.py` | `qagent-qiskit` **包这些函数**，不要重写 |
| qchem extra 已声明 qiskit | `qcchem-qml-md` extras `quantum` / `uqc` | 化学电路走 pin，再进 Qiskit |
| qdata UQC 适配器用 QASM3 | `uqc_adapter.py` 可委托 qiskit | 真机 UQC 是 future pack，不是 P0 |

## 运行时侧（开源 harness，不要自研 loop）

| 事实 | 骨架怎么接 |
|------|------------|
| dsh 插件 = `export name` + `apply(ctx)` | `packages/*/src/index.ts` 已按此开洞 |
| 树外插件 path 必须绝对 | `profiles/qagent/cordis.patch.yml` 用 `${QAGENT_ROOT}`，填的时候展开 |
| `dsh-subagent-codex` 已官方存在，pin `codex@0.147.0` | `S-CODEX-01`；只挂 `algo` |
| 官方子代理 `permissionMode: never` + `inheritsParentContext: false` | **禁止**把 `ionstack_twin_run` 填进这个 mode |
| attended App Server 要自己写 | `S-CODEX-02` P1，空包已立 |
| session 格式 v0 | 科学真源在 qdata store；ELN 事件只投影短字段 |
| `cordis_define` 定义时不问人 | 生产 patch **不挂** tool-cordis |

## 不要开的槽

- 自研 agent loop
- Calibration / shuttle / 南向 MS 工具
- 第三套 MCP 网关（qdata 硬化后由插件直接调 SDK/REST）
- 客户驾驶舱 UI（P0 骑 dsh-web）
