# I-03g · 3080 ELN 行画短 reason

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P |
| 范围 | `qagent/apps/customer-shell/*` · `qagent/tests/test_i03g.py` |
| 状态 | 代码落地，文本测绿。不算过门。 |

## 产品锁

- `paintEln` 在短 `type` / 短交办号之外，若有 `row.reason` 或 `row.payload.reason`，用 **textContent** 再画一截短 reason（`slice(0, 40)`）。class 为 `eln-reason`。
- `ELN_KIND_MAP` 补 `claim_blocked` / `qagent/claim_blocked`，Cirq 拒铸 twin 的 ELN 行看得见（如 `cirq_claim_twin_id`）。
- 仍只用 `GET /api/eln`，没有 POST。HTML 正文不写 `assignment_id`。
- 保持 I-03e：回执下面、`textContent`、无三房间。保持 C-01g：欢迎 `.packs` 含 `pack.kind`。

## 不做什么

不改 `qagent/src/**`、`run_tests.py`、`PROGRESS.md`、`G2_demo.md`、handbooks。不加 POST 追加。不编造 `twin_id`。不 commit。本包只让 ELN 行多画短 reason，**不算** G0 / G2 过门。

## 测

`qagent/tests/test_i03g.py`：`claim_blocked` 进 map；`paintEln` 用 `textContent` 画 `eln-reason`、截到 40；`GET` 无 POST；HTML 无 `assignment_id`；保持 I-03e / C-01g；不宣称 G0/G2 通过；无三房间 / Finder。

```text
PYTHONPATH=src python3 tests/test_i03g.py
PYTHONPATH=src python3 tests/test_i03e.py
PYTHONPATH=src python3 tests/test_c01g.py
```
