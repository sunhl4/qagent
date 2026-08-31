# H-01e · 未就绪打开设置

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | A1 |
| 状态 | 代码落地，离线测绿 |

工作台未就绪时，`chat.turn` / `_out` 的 JSON **必须**带 `open_settings: true`，让 3080 脸去开设置。不造 dsh session。不铸 `twin_id`。

## 合同

- `open_settings` **永远在**。`True` 当且仅当 `load_workplace().ready()` 为 False。
- 未就绪回复仍是「先在设置里接上你们的本地大模型…」。不假装已在 vibe。
- `pending_approval` 只在 snapshot **已经有**时抽出 `approval_id` / `rpc_id` / `tool` / `reason`。缺的不补。没有 `twin_id`。
- 空话仍走 `classify` → empty，不新开 session。

## 测

`qagent/tests/test_h01e_settings.py`：未就绪 `open_settings` True 且 transport 零调用；就绪 temp workplace 为 False；classify/empty 仍在。`test_h01d.py` 仍绿（`QAGENT_DSH_MUX=0`）。
