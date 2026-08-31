# A-03-live · 活 Twin 诚实记录

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | S2 · A-03-live |
| 范围 | 只本笔记 + `qagent/tests/test_a03_live.py` |
| 未改 | `qagent/src/**`（适配器已 fail-close）· `test_a03c.py` · `run_tests.py` · `PROGRESS.md` · customer-shell / `chat.py` / `dsh_session.py` |
| 状态 | 活 Twin `:8765` / `start_twin.sh` **未打**。活 Twin **未证明**（unproven） |

## 产品锁

- 活 Twin **未证明**，除非本笔记抄到一次真实 TwinRun 输出，且里面有 `twin_id`，并且 `provenance` 是 `qccd-twin`。
- 死 home / 死 URL 已由 [A-03c](A-03c_twin_resume.md) 覆盖，必须保持诚实失败。本包不重写那条失败，不改口。
- **只有** ionstack TwinRun 能发 `twin_id`。本包不铸本地 `twin_id`。不换 `circuit_id`（批准后续跑必须沿用同一电路）。
- Aer 的 `provenance` 是 `aer`，**cannot look signed**。IBM / 本地卡也不能冒充 `qccd-twin`。
- **不发明** `accepted:true`。本包不走 mux 批准，未写 `accepted:true`。
- 默认测例只读本笔记。活探函数存在，但除非 `QAGENT_LIVE_TWIN=1` **且** Twin 真回答，否则不调用 TwinRun。

## 活 `twin_id` 规则

活 Twin **未证明**（unproven）。没有真实 TwinRun 输出就写「活 Twin 已通」是造假。本轮不许说「活 Twin 已通」。

`ionstack-serve` checkout 在场、`start_twin.sh` 文件在、`--help`、`GET /v1/twin/identity` 通了但没有 TwinRun `twin_id`、死 URL 抛错，都不是活通。

## 2026-08-27 本轮记录

`QAGENT_LIVE_TWIN` **未设**。按合同 **未打** TwinRun，**未打** `start_twin.sh`。**未写** `accepted:true`。**不许**说「活 Twin 已通」。

| 检查 | 结果 |
|------|------|
| `QAGENT_LIVE_TWIN` | **未设** |
| `QAGENT_TWIN_URL` | **未设**（默认 `http://127.0.0.1:8765`） |
| `QAGENT_IONSTACK_HOME` | **未设** |
| checkout `/Users/shl/Q-software` | **在**。`.venv/bin/ionstack-serve` 可执行（189 B，2026-08-05）。本轮未 export HOME，未拉起服务，不算已通 |
| `scripts/start_twin.sh` | **在**。本轮 **未打** |
| PATH `ionstack-serve` | **无** |
| `GET http://127.0.0.1:8765/` | **不通** |
| `GET /v1/twin/identity` | **不通** |
| TwinRun `POST /v1/twin/run` | **未打** |
| 活 `twin_id` | **无**。不铸 |
| `provenance=qccd-twin` | **无**。没有 TwinRun 回执 |
| 换 `circuit_id` / 换 `circuit.body` | **无**。本包不换 |
| `accepted:true` | **未写** |
| Aer 看起来已签收 | **无**。Aer cannot look signed |

`:8765` 原文（`curl -sS -m 2`）：

```
curl: (7) Failed to connect to 127.0.0.1 port 8765 after 0 ms: Couldn't connect to server
http_code=000
```

`GET /v1/twin/identity` 原文：

```
curl: (7) Failed to connect to 127.0.0.1 port 8765 after 0 ms: Couldn't connect to server
http_code=000
```

本轮没有 TwinRun 发出的 `twin_id`，所以活 Twin **未证明**。死 home 的诚实失败仍归 A-03c。

## 未做

- 不改 `ionstack.py` / `invoke.py` / `run_tests.py` / `PROGRESS.md` / `test_a03c.py` / customer-shell / `chat.py` / `dsh_session.py`。
- 不启动 `scripts/start_twin.sh`（要人设 `QAGENT_IONSTACK_HOME`）。
- 不把 checkout 在场或脚本在场写成已通。
- 不铸本地 `twin_id`。不发明 `accepted:true`。不把 Aer 标成 `qccd-twin`。
- 不换已 pin 的 `circuit_id`。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_a03c.py
PYTHONPATH=src python3 tests/test_a03_live.py
```

活探（可选，且 Twin 必须真回答）：

```bash
cd /Users/shl/nvidia/qagent
export QAGENT_LIVE_TWIN=1
export QAGENT_IONSTACK_HOME=/Users/shl/Q-software
# 已在跑的 Twin → export QAGENT_TWIN_URL=http://127.0.0.1:8765
# 人值守拉起（本笔记没有代跑）：
# bash scripts/start_twin.sh
PYTHONPATH=src python3 tests/test_a03_live.py
```

缺 flag、Twin 不通、TwinRun 没有 `twin_id` + `qccd-twin`：打印 skip，退出 0。不铸本地 `twin_id`。不发明 `accepted:true`。不换 `circuit_id`。没有 TwinRun 输出里的 `twin_id` 就不许写「活 Twin 已通」。
