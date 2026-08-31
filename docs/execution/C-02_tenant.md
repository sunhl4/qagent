# C-02 · 租户隔离与外发回执

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-26 |
| 角色 | P |
| 范围 | assignment 模型 / store / service · `shell_http` 读 `X-QAGENT-TENANT` · `qagent/tests/test_c02.py` |
| 状态 | 代码落地，隔离测绿 |

## 产品锁

- 交办带可选 `tenant_id`。来源是请求头 `X-QAGENT-TENANT`，或创建时 body 的 `tenant_id`。头优先。
- 空租户是组内 / 工作台：和现在一样，**看见全部行**（含未打标的旧行）。这样 `run_tests.py` workbench 里 `create()` 不带 tenant、再 `GET /api/assignments` 仍能列到刚建的交办。
- 租户一旦有值，list / get / receipt 只回本租户。客户 A 拿客户 B 的 `assignment_id`：服务层 `AssignmentError`，HTTP `404`。不泄露「存在但不是你的」。
- 默认 `tenant_id=""`，不是房间名 `lab`。未打标的行对已设租户的调用方不可见。
- 外发回执仍是短导出：`qagent/receipt` + `qagent.receipt/v1`。有租户才写 `tenant_id`。没有电路 body / QASM、没有 token / secret / api_key。不另做一套回执。
- 独立核验仍是 `python3 scripts/verify_receipt.py receipt.json`。多一个 `tenant_id` 字段会进 hash，脚本不 `import qagent`，不用改。

## 工作台为何仍绿（概念核）

`test_workbench` 用 `create(room="lab", …)`，不传 `tenant_id`，HTTP 也不带头。空调用方走 staff 路径，list / get / receipt / cancel 与改前一致。`/api/chat/status` 仍叫 `chat_status`，没有第三套 loop，没有本地铸造 `twin_id`。

## G2 演示（两客户）

1. 客户 A 带头 `X-QAGENT-TENANT: cust-a` 建交办。客户 B 用 `cust-b` 建另一条。
2. B 的在办列表没有 A。B 打开 A 的 id：404。
3. 导出 A 的回执：可见 `tenant_id`，看不见电路正文和密钥。换一台机器跑 `verify_receipt.py`。

## 不做什么

不改 `chat.py` / `dsh_session.py` / `eln.py` / `qdata.py` / customer-shell / `product_eval.py` / `run_tests.py` / `PROGRESS.md`。不加第三套 agent loop。不 commit。`run_tests.py` 挂测留给调度。
