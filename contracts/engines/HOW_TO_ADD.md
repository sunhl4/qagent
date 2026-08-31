# 以后加一个软件包

不要新写 agent。先留端口，再接线。政策与评测会自动看见。

Cirq **已经**在 `engines[]` 且 wired，是互通范例。`provenance` 不是 `qccd-twin`，不许发 `twin_id`。再加一个包（Pennylane / 真机）仍按本页步骤：**先 reserved**，不要一上来写进 `engines[]`。只有 ionstack TwinRun 能发 `twin_id`。

1. 在 `catalog.json` 的 `reserved_engines` 加一条：`id` / `kind` / `home` / `tools` / `identity_fields` / `vibe`。`status` 写 `reserved`。不要一上来写进 `engines[]`。
2. 每个新工具在 `contracts/tools/` 放 schema，并写入 `tools/catalog.json`。
3. 在 `contracts/ports.json` 加 port，方法对上工具名；`src/qagent/models/ports.py` 加 Protocol；`adapters/reserved.py` 先 `fill()`。
4. `packages/qagent-<id>/` 照现有插件抄一份，`execute` 调 `invoke()`，不要 import 那一家。
5. `contracts/slots.json` 加槽；`presets.json` 的 `lab.visible_tools` 加上新工具（若实验室该看见）。
6. `policy.json` 加 allow/ask/deny。失败闭合：没规则 = deny。
7. 若产生电路：只通过 `qagent_pin_circuit` 换成 `circuit_id`，不要把 QASM 全文塞进对话。
8. 若不是我们的机器：输出**禁止**出现 `twin_id`。Aer / IBM Runtime / 别人的 backend 一律 `provenance != qccd-twin`。
9. 加一条 `contracts/eval/E*.json`。
10. `python tests/run_tests.py` 必须绿。**未接线前**围栏禁止 `import` 该核。`qagent/src` 不许 `import qdata/ionstack/qchem/qiskit`。

句柄只有 `circuit_id` / `asset_id` / `twin_id`。不要发明第四个：

| 东西 | 字段 |
|------|------|
| 数据 / 配方 | `asset_id` |
| 跨引擎电路 | `circuit_id` |
| 我们的 QCCD | `twin_id` |
