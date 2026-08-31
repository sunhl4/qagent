# H-01k · TwinRun 认 pin 的 circuit_id

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | A1 |
| 范围 | `adapters/ionstack.py`、`packages/qagent-twin/src/index.ts` |
| 状态 | 完成。dsh 不再让模型空参上机。`circuit_id` + `mode=pipeline` 可跑。不算 G0 过门。 |

## 缺口

H-01j 产品「批准」后 `ionstack_twin_run` 参数是 `{}`，回 `S-TWIN-02`。pin 只回 `circuit_id`，合同却要 `circuit.body`。交办路径本来就带 `DEFAULT_CIRCUIT`。不铸 `twin_id`。

## 完成线

- `_circuit()`：有 `circuit.body` 用它；否则用 pin 的 logical；再否则用与交办相同的 2 比特回退。
- `{}` 仍失败。
- dsh 注册必填 `mode` / `shots` / `circuit_id`。
- invoke 活路径：`mode=pipeline` + `shots=8` + pin 的 `circuit_id`，`approved=True` → 真 `twin_id=5c9ce47cda91d673598ba1283fed4e5ab4c1c17d2c770245ecab2534e3e071a5`，`provenance=qccd-twin`。
- 产品 session `b70510e6`：「扫氢分子」后两次 `qdata_run_recipe` 高 shots 待批，均 `allowed-once`。随后 `ionstack_twin_run` `{"circuit_id":"a2_chem_pes","mode":"pipeline","shots":10000}`，`approval_id` `ca95b4f8` → `allowed-once`。pin `a2_chem_pes` 不存在，当时走回退 2 比特。Twin 回真 `twin_id=5c9ce47cda91d673598ba1283fed4e5ab4c1c17d2c770245ecab2534e3e071a5`，`shots_actual=10000`，`provenance=qccd-twin`。不是 `{}`，没有假 `twin_id`。
- H-01l 起：无 `logical.body` 的 pin **不再**回退 H+CX，诚实失败、不发 `twin_id`。
- 不假 `twin_id`。不算 G0。
