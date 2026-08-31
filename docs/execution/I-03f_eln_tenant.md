# I-03f · GET /api/eln 按调用方租户过滤

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | A2 |
| 范围 | `entrypoints/shell_http.py` · `services/eln.py` 过滤辅助 · `tests/test_i03f.py` · `INTERFACES.md` 半句 |
| 状态 | 代码落地，文本测绿 |

## 产品锁

- `GET /api/eln` 仍只读。无 POST 追加。回显前仍 `short_payload`。不铸 `twin_id`。
- **空租户**（无 `X-QAGENT-TENANT`、无 body tenant）：与 I-03d 完全一样，看见全部事件。`dispatch("GET", path)` 不带头必须仍绿。
- **已设租户**：只回「交办属于该租户」的事件。`list_assignments(tenant_id=)` 得可见交办号，再按事件 `assignment_id` / `belongs_to_assignment` 过滤。
- 没有交办号的事件对已设租户**不可见**（组内流水，不漏给客户）。
- 客户 A 不得看见客户 B 交办上的 pin / estimate / assignment。别人的交办从列表拿掉，不要 404。
- `?assignment_id=` 仍可用：先按交办过滤，再套租户可见集。别人的交办 → 空列表，不报错、不编 `twin_id`。
- `dispatch()` 不写本地 `status =`（`chat_status` 导入名不动）。不扩 `agent.py`。

## 过滤规则

1. `_eln_http(query, headers)` 读 `_caller_tenant(headers)`。
2. 租户为空：直接 `read_eln(assignment_id=)` + `short_payload`。**不过**可见交办集——否则未入库交办号上的旧事件会消失。
3. 租户有值：`visible = {row.assignment_id for row in list_assignments(tenant_id=)}`，再用 `filter_eln_for_assignments`（内部 `belongs_to_assignment`）留下属于可见集的行。
4. 可见集为空、或事件没有 `assignment_id`、或交办号不在可见集：该行不出现。HTTP 仍是 200 `{events: [...]}`。

## 写到哪里

- `dispatch` 的 GET `/api/eln` 把已有 `headers` 传给 `_eln_http`。
- `services/eln.py` 只加 `filter_eln_for_assignments`，不改五类 append / fork 丢 `twin_id`。
- `INTERFACES.md` ELN 只读行补「已设租户只见本租户交办事件」。

## 不做什么

不改 customer-shell / `chat.py` / `dsh_session.py` / `run_tests.py` / `PROGRESS.md` / `test_i03.py` / `test_i03d.py` / `test_c02.py`。不加 POST 追加。不 commit。不 `import qdata`。

## 测

`qagent/tests/test_i03f.py`：空租户仍见 pin+estimate；租户 A 只见 A；无交办号对已设租户不可见；别人的 `?assignment_id=` 空列表；无 POST；无密钥 / 电路正文 / 假 `twin_id`。`test_i03d` / `test_i03` / `test_c02` 仍绿。

```text
PYTHONPATH=src python3 tests/test_i03f.py
PYTHONPATH=src python3 tests/test_i03d.py
PYTHONPATH=src python3 tests/test_i03.py
PYTHONPATH=src python3 tests/test_c02.py
```
