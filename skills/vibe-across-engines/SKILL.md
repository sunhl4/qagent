---
name: vibe-across-engines
description: 跨引擎 vibe。默认建议，不是唯一入口。Skill 触发也不能绕过 ask。lab/sign 量子轨。
---

# 跨引擎 vibe

科学家用自然语言交办。下面是**默认建议，不是唯一入口**。Skill 触发也不能绕过 ask。模型按这句话选公司工具，不要每次都走同一条配方。可以先查手册、先估计、跳过 Aer，但不能破硬轨。不要把电路全文塞进对话。

对人说话时只给短结论，可用 Markdown 标题、列表、表格。不要报工具名、配方名、scenario 名，也不要报调用流水。不要主动写映射名和 Pauli 展开，除非人要公式。人要公式时用 `\(...\)` 行内、`$$...$$` 独立成行，脸会渲染；不必改成 Unicode。不要把 `circuit_id` / `asset_id` / `twin_id` / session 句柄念给客户听；说「这份线路」「这份数据」「已签收」。客户要拿走线路时，让他点脸上的「下载这份线路」，不要 `qiskit_export_circuit`。电路图由脸用 `circuit_id` 画，导出线路不会让图更好。

1. `qagent_list_engines` — `engines[]` 是已接线（五包打头，Cirq 已 wired，`kind=interop`，`provenance` 不是我们的机器，不发 `twin_id`）。Pennylane 在 `reserved_engines`，`status=reserved`，不在目录 / `engines[]`。
2. 化学：`qchem_run` 或 `qdata_run_recipe` → `asset_id`。scenario / recipe 跟人说的任务对齐。人没点名氢分子/UCCSD 就不要 `uccsd_pauli`。未接线就是 `not_wired`。不要把 `a2_chem_pes` 当 `circuit_id`。
3. 需要跨引擎句柄：`qagent_pin_circuit` → `circuit_id`。只回短 id。
4. 可选 Qiskit：`qiskit_transpile` / `qiskit_aer_run`。Aer 的 `provenance` 必须是 `aer`，**没有** `twin_id`。
5. 可选 `ionstack_compile_estimate` → 只有 `makespan_ns`，没有签收 `ok`。
6. 要我们的机器：`ionstack_twin_run`（ask）→ 只有这时才有 `twin_id`。必须已经有真 `circuit_id`。
7. 宣称优势：`qdata_dequant_gate` 的 `b3.verdict`。
8. 查阅：`qccd_docs_search`。空库诚实。

## 禁止

- CAL / shuttle / 南向符号
- 把 Aer / IBM 写成同一 `twin_id`
- 在官方 Codex `permissionMode: never` 里上机
- 把 Pauli / QASM / bitstrings 全文塞进对话
- 把每一次对话都做成 H₂ UCCSD 电路图
- 电路图由脸用 `circuit_id` 画。不要为了图去 `qiskit_export_circuit` 拉 QASM
