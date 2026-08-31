# C-02f · chat / dsh session 按租户分开

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P |
| 范围 | `dsh_session_store.py` · `services/chat.py` · `shell_http.py` · `tests/test_c02f.py` · `INTERFACES.md` 半句 |
| 状态 | 代码落地，离线测绿 |

## 产品锁

- **空租户**（无 `X-QAGENT-TENANT`）：与现在完全一样。`turn` / `status` / `reset_chat` 默认 `tenant_id=""`。`load_session_id()` / `save_session_id()` / `clear_session_id()` 无参调用保持兼容。`test_h01d` / `test_h01e_settings` 仍绿。
- **已设租户**：各租户自己的 dsh session，互不复用。A 的 `turn` / `status` 读不到 B 存下的 sessionId。
- 批准仍走**该租户**已有 session，不 `session.create` 当批准。不新开第三套 loop。不扩 `agent.py`。
- 不铸 `twin_id`。不发明第四个句柄。句柄仍只有 `circuit_id` / `asset_id` / `twin_id`。
- `POST /api/agent/reset` 只清调用方那条：空租户 unlink staff 文件（与现在一致）；已设租户只丢掉自己的桶。

## 存储形状

空租户仍写现有文件 `QAGENT_DSH_SESSION_FILE`（默认 `.qagent/dsh-session.json`），形状不变，权限 **0600**：

```json
{
  "sessionId": "sess_staff"
}
```

已设租户走**旁路** `dsh-session.tenants.json`（与 staff 文件同目录、同 stem），权限 **0600**。键先 `normalize_tenant`，`/` `\` `\0` 换成 `_`，只当 JSON 键，不当路径：

```json
{
  "by_tenant": {
    "cust-a": "sess_a",
    "cust-b": "sess_b"
  }
}
```

空租户 `clear_session_id()` 仍 unlink staff 文件，不碰旁路。已设租户 reset 只删自己的 `by_tenant` 键；桶空则 unlink 旁路。

## HTTP

- `_chat_http` 与 `GET /api/chat/status` 把 `_caller_tenant(headers)` 传进 `turn` / `status`。
- `POST /api/agent/reset` 把同一调用方租户传进 `reset_chat`。

## 不做什么

不改 customer-shell、`eln.py`、`test_h01d.py`、`test_h01e_settings.py`、`run_tests.py`、`PROGRESS.md`、`dsh_session.py`。不加第三套 agent loop。不 commit。不 `import` 科学核。

## 测

`qagent/tests/test_c02f.py`：空租户现有 API 仍是 `{sessionId}`；A/B 各存各的；dispatch 带头后 session 键分离；reset 空租户仍清 staff 文件。`QAGENT_DSH_MUX=0`。

```text
PYTHONPATH=src python3 tests/test_c02f.py
PYTHONPATH=src python3 tests/test_h01d.py
PYTHONPATH=src python3 tests/test_h01e_settings.py
PYTHONPATH=src python3 tests/test_c02.py
PYTHONPATH=src python3 tests/test_i03f.py
```
