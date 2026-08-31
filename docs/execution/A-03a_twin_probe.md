# A-03a · Twin home 探活

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-26 |
| 角色 | S2 |
| 约定 home | `/Users/shl/Q-software`（ionstack / Q-software） |
| REST | `QAGENT_TWIN_URL` 默认 `http://127.0.0.1:8765` |

## 探活

| 检查 | 结果 |
|------|------|
| `QAGENT_IONSTACK_HOME` 环境变量 | **未设** |
| checkout | **在** · `/Users/shl/Q-software` |
| `ionstack-serve` | **在** · `/Users/shl/Q-software/.venv/bin/ionstack-serve` |
| `GET /v1/twin/identity` | **不通** · `Failed to connect to 127.0.0.1 port 8765` |
| `twin_id` | **无**。适配器在 REST 失败时不得本地铸造 |

启动命令（有人值守时，本探活**没有**拉起服务）：

```bash
export QAGENT_IONSTACK_HOME=/Users/shl/Q-software
bash qagent/scripts/start_twin.sh
```

`ionstack-serve --help` 只接受 `--host` / `--port` / `--backend`。preset 仍走环境 `IONSTACK_TWIN_PRESET`（脚本默认 `t_junction`）。

## 诚实错误（给产品文案）

Twin REST 不通时，身份只许：

```json
{ "preset": "t_junction", "n_qubits": 8, "live": false }
```

TwinRun 只许失败，例如：

> TwinRun REST 没有返回 twin_id 和 counts；不会在本地伪造 twin_id。

G1 允许这种诚实失败。G2 不得对客户假装已签收。

## A-03b 下一步

`ionstack_twin_identity` 输出只留 `preset` / `n_qubits` / `live`。已在适配器里，活路径要再打一次 `:8765`。
