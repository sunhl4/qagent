# H-03d-live · 活「换默认模型，下一句人话生效」诚实记录

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | A1 · H-03d-live |
| 活实例 | 已在跑的 `dsh --profile qagent` · `http://127.0.0.1:3081` |
| 脸 | `GET /api/workplace` · `http://127.0.0.1:3080` |
| 范围 | 只本笔记 + `qagent/tests/test_h03d_live.py` |
| 未改 | `qagent/src/**`（`apply_env` 已写 `DEEPSEEK_MODEL`）· `test_h03.py` · `run_tests.py` · `PROGRESS.md` · workplace store · customer-shell · `chat.py` · `dsh_session.py` |
| 状态 | 活「换默认模型，下一句人话生效」**未打** / **未证明**（unproven）。**不许**说「活模型切换已通」 |

## 产品锁

- 离线写入已由 [H-03c](H-03c_model_switch.md) 覆盖：`apply_env` 把 workplace 模型写进进程 `DEEPSEEK_MODEL`。那不是活 dsh 下一句已换模。
- 活切换 **未证明**（unproven），除非 3081 `host.describe`（或同等：`session.models` 的 `current.model`）在 **apply_env 之后** 露出**新**模型。只看见当前默认模型、只看见进程 env、只看见 `dsh.env`，都不够。
- 没有「apply_env 之后的新模型」就写「活模型切换已通」是造假。本笔记拒绝这句话。
- `GET /api/workplace` **永不**回密钥值。JSON 里不能出现 `llm_api_key` / `hpc_secret` / `quantum_secret` 的值，只有 `has_*`。
- 不铸 `twin_id`。不发明工具调用。不拿编造的 `rpcId` 去 `POST /api/respond`。
- 默认测例只读本笔记 + 隔离的 GET。活探函数存在，但除非 `QAGENT_LIVE_MUX=1` **或** `QAGENT_LIVE_H03=1` **且** 3081 活着，否则不调用。`host.describe` 不可用：诚实 skip。

## 活换模规则

活「换默认模型，下一句人话生效」**未打** / **未证明**（unproven）。要过门必须同时有：

1. 换了默认模型并走了 `apply_env`（本包**不许**写 workplace store，所以本轮没换）。
2. 之后 3081 `host.describe`（或同等）里的 `model` 变成**新**模型。
3. 下一句人话按那个新模型走。本轮**没有**打下一句人话。

缺任一条就仍是未打。`apply_env` 写进**本进程** env，不等于 3081 已经换模。

## 2026-08-27 本轮记录

环境里 `QAGENT_LIVE_MUX` / `QAGENT_LIVE_H03` **未设**。测例默认不打 3081。笔记作者对着已在跑的 3081 读了 `host.describe`（只读）。**未写** workplace store。**未**对活实例 `apply_env` 换模。**未**打下一句人话。因此活切换 **未打**。

| 调用 | HTTP | 结果 |
|------|------|------|
| `GET http://127.0.0.1:3081/` | **200** | dsh-web 活着 |
| `POST /api/host.describe` | **200** | cwd=`/Users/shl/nvidia/qagent`，provider=`deepseek-official`，model=`deepseek-v4-flash` |
| `GET http://127.0.0.1:3080/api/workplace` | **200** | `ready=false`。`llm_model` 空。无 `llm_api_key` / `hpc_secret` / `quantum_secret` 键。`has_*` 均为 false。**没有密钥值** |
| `session.list` | **200** | `result.ok=true` |
| `session.create` `{agentPreset:"qagent"}` | **200** | `sessionId=session-9e3a37c0-e6fa-4573-82bc-ddb766ec2aef`。无 `twin_id` |
| `session.models`（同等） | **200** | `current.provider=deepseek-official`，`current.model=deepseek-v4-flash`。这是**当前**模型，**不是** apply_env 之后的新模型 |
| `session.prompt` 下一句人话 | **未打** | 不发明工具调用 |
| `apply_env` 换默认模型 | **未做** | 不许写 workplace store |
| `host.describe` 换模后复查 | **未打** | 没有「之后的新模型」 |
| `POST /api/respond` | **未尝试** | 不铸 `rpcId` |

`host.describe` 原文（当前模型，不是切换后）：

```json
{"cwd":"/Users/shl/nvidia/qagent","provider":"deepseek-official","model":"deepseek-v4-flash"}
```

3081 活着，且 `host.describe` 可用，只证明能读到**当前**官方默认 `deepseek-v4-flash`。workplace 这边模型是空的，也没有对活实例做 apply_env。所以「换默认模型，下一句人话生效」**未打**。**不许**说「活模型切换已通」。

写完测例后补打一次 gated 活探（`QAGENT_LIVE_H03=1`）：`host.describe` 仍是 `deepseek-v4-flash`；又建了 `session-b4f332a5-e0db-4294-b5c9-850d29e0ae47`；`switched=false`；未 `POST /api/respond`。结论不变。

## 未做

- 不改 `qagent/src/**` / `test_h03.py` / `run_tests.py` / `PROGRESS.md` / workplace store / customer-shell / `chat.py` / `dsh_session.py`。
- 不铸 `twin_id`。不发明第四句柄。不调 `ionstack_twin_run`。
- 不把当前 `deepseek-v4-flash`、进程 `DEEPSEEK_MODEL`、或 H-03c 离线绿测写成活切换已通。
- 默认测例不要求 3081。活探要 `QAGENT_LIVE_MUX=1` 或 `QAGENT_LIVE_H03=1`，且 3081 必须活着；`host.describe` 不可用则 skip。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_h03.py
PYTHONPATH=src python3 tests/test_h03d_live.py
```

活探（可选，且 3081 必须活着）：

```bash
cd /Users/shl/nvidia/qagent
QAGENT_LIVE_H03=1 PYTHONPATH=src python3 tests/test_h03d_live.py
# 或：QAGENT_LIVE_MUX=1 PYTHONPATH=src python3 tests/test_h03d_live.py
```

3081 宕、或 `host.describe` 不可用：打印 skip，退出 0。不编造换模后的新模型。不 `POST /api/respond`。没有 apply_env 之后的新模型就不许写「活模型切换已通」。
