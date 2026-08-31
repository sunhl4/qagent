# G-02 · 可诊断性与一机状态面

对照会话里对框架 / 一机 UI 的反思。不换合同、不改工具名、不发明第四句柄、不把槽位号当原因。

## 做成什么样

| 层 | 落地 | 明确不做 |
|----|------|----------|
| 错误目录 | `contracts/errors.json` + `GET /api/errors`。kind / hint / retryable / health | 把 invoke HTTP 加肥；改 I-01h 四键 |
| 槽位 | `S-TWIN-03` 仍是填充位。同槽可拆 missing / unready / refused | 把槽位号改成用户错误码 |
| 预设 | `list_engines` 带 preset 仍切换（锁）。回 `switched` / `hint`。`GET /api/preset` 只读；`POST /api/preset` 要 token | 新工具名 `qagent_set_preset` |
| 健康四灯 | twin / estimate / qdata / asks。`live` 不再单独代表可预估 | 预估失败硬挡批准 |
| 预检 | `estimate_ok` / `estimate_ns` 进 checks。`ok` 公式不变 | 回显 identity / 第三句柄值 |
| 知识 | handbook `errors.md` + `workspace-index.md`。不改 `qccd_docs_search` schema | 第三种 source |
| 一生 | `gov_face.life` 只出中文阶段名 | JS 里写工具名 |
| 钉住 | qiskit 源必须有 qasm3 或 logical | 用空 asset_id 凑过 pin |
| 导出 | 必须带 circuit_id（或 context 别名） | 隐式会话电路 |
| P2 | `contracts/engine_forms.json` 声明式草稿 | 本轮用规范生成表单 |

## 硬轨

北向仍是 mode / shots / circuit.body。CAL / shuttle 不进工具。Aer / IBM 出处不得冒充孪生签收。3080 JS 仍禁止 `ionstack_twin_run` 与 `twin_id=`。
