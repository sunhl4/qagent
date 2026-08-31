# C-02h · 空 `?tenant=` 清回组内

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P · C-02h |
| 范围 | `qagent/apps/customer-shell/app.js` · 本笔记 · `qagent/tests/test_c02h.py` |
| 未改 | `chat.py` · `assignment.py` · `shell_http.py` · `agent.py` · `run_tests.py` · `PROGRESS.md` · `G2_demo.md` · ionstack 核 · workplace 密钥 |
| 状态 | 空 `?tenant=` 删 `QAGENT_SHELL_TENANT`，组内不再带头。空 `?role=` / `?role=staff` 删客户角色。对话气泡仍 `send("批准")`。**不算 G0**。**不算 G2**。未 commit。 |

## 产品锁

- G2：空租户是组内，看见全部。点过 `?tenant=cust-a` 之后，地址栏被 `replaceState` 清掉，再开不带 query 的组内 URL 仍会带着旧租户头。本包让空 `?tenant=` 显式清掉。
- `headers()` 仍是有值才带 `X-QAGENT-TENANT`。空租户不带头。
- 空 `?role=` 或 `?role=staff` 清 `QAGENT_SHELL_ROLE`，密钥栏回到组内。
- 在办「批准上机」仍走 HTTP `assignmentAction`。聊天气泡仍 `send("批准")`。源码不出现字面 `/approve`。
- 已签收回执仍可下载 / 核验。不编 `accepted:true`。不伪造 `twin_id`。
- **不算 G0 / G2**。人还没按客户剧本走完。
- skip 当绿 = 没做完。未 commit。不伪造上机句柄。

## 改了什么

`token()`：`params.has("tenant")` 时，有值写入 `QAGENT_SHELL_TENANT`，空值 `removeItem`。`params.has("role")` 同样，空或 `staff` 清客户角色。

`paintReceipts` 只对画出的前 8 行算 `receiptKey`。超过 8 条未签收时不再每轮清空列表，核验行才留得住。

下载 / 核验改走 `loadReceiptRaw`：把 `GET …/receipt` 原文原样 POST，不再 `JSON.parse` 再 `stringify`。JS 会把 `makespan_ns: 3040.0` 收成 `3040`，哈希对不上。`verify_receipt.py` 仍吃这份原文。

浏览器：`?tenant=c02h-a` 只见 `asg_03357af1967a`（短号 `7af1967a`），回执空。空 `?tenant=` 后 `QAGENT_SHELL_TENANT` 为 null，组内看见 10 条在办和 6 条已签收。脸上点核验 `asg_b281b611c8f6` 写 `ok`，轮询后仍在。`verify_receipt.py` PASS `sha256:bd72c528fb9c53bf50856c20041b34e5d3cfe5f232f834558d00c718859ba0f1`。不算 G2。

## 不算什么

- **不算 G0**。ready 仍 false。
- **不算 G2**。只修好组内在客户演示后回得去。两位客户隔离本来就能用带值的 `?tenant=`。
- 不算活 mux `accepted:true`。空 mux 仍不编。
- 未改 `chat.py`。未 commit。`send("批准")` 气泡不动。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_c02h.py
PYTHONPATH=src python3 tests/test_c02d.py
PYTHONPATH=src python3 tests/test_c01d.py
PYTHONPATH=src python3 tests/test_c01m.py
PYTHONPATH=src python3 tests/run_tests.py
```

空 `?tenant=` 仍写死租户必须失败。skip 当绿 = 没做完。不 commit。
