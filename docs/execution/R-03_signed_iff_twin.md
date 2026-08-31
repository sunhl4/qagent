# R-03 · signed iff twin + 回执

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-26 |
| 角色 | A2 |
| 状态 | 不变式落地，测绿 |
| 代码 | `qagent/src/qagent/models/assignment.py` · `services/assignment.py` · `scripts/verify_receipt.py` |

## 不变式

`status=signed` **仅当** 同时有 `handles.twin_id` 和 `sources` 含 `qccd-twin`。缺一不可：

- 只有句柄、来源是 Aer / 本地卡 → `can_sign` 为假，`validate_status("signed", …)` 抛 `AssignmentError`。
- 只有 `qccd-twin`、没有 `twin_id` → 同样不能看起来已签收。
- 适配器不得本地铸造 `twin_id`。本包测里的 `twin_fixture` 只是模型层夹具。

已签收不可取消：`cancel()` 在 `status=signed` 时抛 `AssignmentError`（`signed work cannot be cancelled`），状态保持 `signed`。

`can_sign` 为真不会自动改 status；只有 TwinRun 成功路径把 status 写成 `signed`。

## 回执 schema（不要第二套）

封条后的 JSON 同时带两个字段，**不是**两套合同：

| 字段 | 值 | 谁写 |
|------|----|------|
| `kind` | `qagent/receipt` | `receipt_payload` |
| `schema` | `qagent.receipt/v1` | `seal_receipt` |

计划文案写的 `qagent.receipt/v1` 是 **schema**。已有消费者（HTTP `GET /receipt`、`POST /receipts/verify`、`scripts/verify_receipt.py`）认 schema + `sha256:`。不要把 `kind` 改成 `qagent.receipt/v1`。

核验：重算除 `receipt_hash` 外的 canonical JSON。改 shots 或改 hash 都会 `ok=false`。`signed` 或 `status=signed` 还必须能通过 `can_sign`（句柄 + `qccd-twin`）。独立脚本是 stdlib，不 `import qagent`。

## 回执不含的东西

短导出：句柄、来源、shots、status、lanes、identity 的 `preset` / `n_qubits` / `live`、b3、makespan。没有电路 `body` / QASM、Pauli、bitstrings、`counts`、token / secret。

## 测

`qagent/tests/test_r03.py`：`can_sign` 双条件、无 twin 不能 signed、已签收不可 cancel、封条后改 shots / 改 hash 失败、kind/schema 与现网一致、导出无密钥。

## 未做

- R-03c 脸（未签收栏视觉）在 customer-shell，本包不许改。
- `reject()` / `run()` 仍可能把已签收交办改离 `signed`；本包只锁 `cancel()`。
- 未打 Twin REST；没有活 `twin_id` 端到端签收。
