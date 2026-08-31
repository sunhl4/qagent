# H-01l · H₂ UCCSD 电路图，不回退 H+CX

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | 调度落地 |
| 范围 | `adapters/qchem.py`、`adapters/ionstack.py`、`adapters/pin.py`、`apps/customer-shell`、`packages/qagent-qchem`、`skills/h2-uccsd` |
| 状态 | 完成。人要 H₂ UCCSD 和电路图时 pin 4 比特线路并画图。无 `logical.body` 不回退 H+CX。不算 G0 过门。 |

## 缺口

产品把配方名当成 `circuit_id`，H-01k 静默回退 2 比特 H+CX，脸上只剩「批准上机」。没有 UCCSD，没有电路图。

## 完成线

- `qchem_run` `scenario=uccsd_pauli` 走包装脚本，pin 真 `circuit_id`，`n_qubits=4`，`ansatz=uccsd`。
- 产品 session `session-55962df0-51cc-4d69-b256-9bb70ae127d1`：人说「要一个 H2 的 UCCSD，以及电路图」。脸画出 `circ_acaec12522be`，4 比特 · 194 门 · uccsd。没有假 `twin_id`。
- `GET /api/circuits/<id>` 回门列表，无 `qasm3` / `body` / `twin_id`。3080 画 SVG 电路图。
- 未知或无 body 的 `circuit_id` 诚实失败，**不回退** H+CX，不发 `twin_id`。
- 「批准上机」仍在 JS，只在 TwinRun 待批时用。上机是另一步。
- `qagent/src` 无 `import qchem`。
- 不假 `twin_id`。不算 G0。
