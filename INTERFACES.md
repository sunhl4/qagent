# 接入接口

底层软件包（`qdata`、`qcchem-qml-md`、`Q-software` / ionstack）**不要改、不要 `import`**。Qagent 端口已接线：REST / CLI / 本仓合同 store。工具名不动。

## 现在能跑

| 面 | 行为 |
|----|------|
| `decide()` | 政策：allow / ask / deny |
| `invoke("qagent_list_engines")` | 五包打头且 `wired`；Cirq 在其后，`kind=interop`，`provenance=cirq`，不发 `twin_id`。Pennylane 在 `reserved_engines`，不在 ids。不算接线 |
| `invoke("qagent_pin_circuit")` | 只回 `circuit_id` |
| `qdata_*` | 有 CLI 则 `qdata run`（`source=qdata-cli`）；否则本地卡 `qagent-local-card`。设了 `QAGENT_QDATA_URL` 的 job 走 HTTP，不通就失败 |
| 交办 | `.qagent/assignments.jsonl`；`status=signed` 当且仅当活 `twin_id` + `qccd-twin` |
| 对话 | `POST /api/chat` 转发人话到 dsh `session.prompt`；`GET /api/chat/status` 短轮询同一 session 的气泡/工具卡。已设租户各一条 session。无模型先诚实。**不**走 `services.agent._loop`。上机仍要 `QAGENT_SHELL_TOKEN` |
| mux peek | 历史在等批准但没有 mux `rpcId`（含 `pending_approval is None`）时，`snapshot` 短读 mux。`GET` 426 则 WebSocket。无帧则 pending 仍是 `None`，不铸 id。作答仍 `POST /api/respond`。`QAGENT_DSH_MUX=0` 跳过 |
| 工作设置 | `GET|PUT /api/workplace`：本地模型、超算/量子计算机账户、知识库、软件包目录。密钥不回显 |
| `QAGENT_CLOUD_URL` | 设置里的 `cloud_url`；空则未配置、从进程 unset。不进 `dsh.env`。`qiskit_ibm_run` 仍 deny |
| 回执 | `GET /api/assignments/{id}/receipt` → `qagent.receipt/v1` + `sha256:`；`POST /api/receipts/verify`；独立核验 `python3 scripts/verify_receipt.py receipt.json` |
| `ionstack_twin_identity` | 只回 `preset` / `n_qubits` / `live`，不发 `twin_id` |
| `ionstack_twin_run` | lab/sign 先 ask；`approved=True` 后只有活 Twin REST 发 `twin_id`，失败不本地伪造 |
| `qiskit_aer_run` | `provenance=aer`，无 `twin_id` |
| `ionstack_compile_estimate` | `makespan_ns`，无 `ok`；`QAGENT_ROUTE_BACKEND` 换后端 |
| ELN | `.qagent/eln.jsonl` |
| ELN 只读 | `GET /api/eln` → `{events}`；可选 `?assignment_id=`。已设租户只见本租户交办事件。密钥与电路正文不回显。无 POST 追加。不铸 `twin_id`。`claim_blocked` 带短 `reason` |
| import 围栏 | `src/` 与 `packages/` 禁止 `import qdata/ionstack/qchem/qiskit` |

```bash
cd qagent
PYTHONPATH=src python -m qagent.entrypoints.eval_cli
PYTHONPATH=src python -c "from qagent import invoke; print(invoke('qdata_run_recipe','lab',{'name':'a2_chem_pes'}))"
```

TwinRun 未批准：`status=needs_ask`。批准后：`invoke(..., approved=True)`。工作台 `approved=true` 要带 `QAGENT_SHELL_TOKEN`（`X-QAGENT-APPROVE-TOKEN` 或 `X-QAGENT-DEBUG-TOKEN`）。

人入口：`bash scripts/start_ui.sh` → `http://127.0.0.1:3080`。先在设置里接本地模型。完整改文件/跑命令仍用 `bash scripts/start_runtime.sh`（dsh `:3081`）。活 qdata：`bash scripts/start_qdata.sh`。加开源包：`contracts/engines/HOW_TO_ADD.md`。

preset 真源是 `.qagent/active_preset`（可用 `qagent_list_engines` 的 `preset` 参数切换，带参会切会话并回 `switched`），其次才是 `QAGENT_PRESET`。只读用 `GET /api/preset`。显式切换 `POST /api/preset`（要 token）。`boot` 只挂轨工具；TwinRun 在 boot 与 `profiles/qagent-minimal` 里不可见。

治理 HTTP（短字段，不回显密钥 / 不回第三句柄的值）：`GET /api/doctor`、`GET /api/gov/face`（含四灯 `lamps` 与 `life`）、`GET /api/errors`、`GET /api/preset`、`POST /api/preset`（要 token）、`GET /api/asks`、`GET /api/usage`、`GET /api/replay`、`POST /api/handoff`（要 token）、`POST /api/savepoint`、`POST /api/safe-mode`。槽位号不是错误原因，查 `contracts/errors.json`。

```bash
PYTHONPATH=src python -m qagent.entrypoints.doctor_cli
PYTHONPATH=src python -m qagent.entrypoints.gov_cli handoff --handles '{"circuit_id":"circ_x"}' --intent 'sign next'
```

## 三个句柄

| 字段 | 谁发 | 谁不许发 |
|------|------|----------|
| `asset_id` | qdata / qchem | — |
| `circuit_id` | `qagent_pin_circuit` | 对话里不要塞 QASM 全文 |
| `twin_id` | **只有** ionstack | qiskit Aer / IBM / 任何外机 |

## 端口

真源：`contracts/ports.json`。

| 端口 | 接线 |
|------|------|
| `catalog` / `pin` | 本仓合同 |
| `qdata` | CLI `qdata run` 或 HTTP `:8787`；不通则诚实失败或本地卡（看是否设了 URL/CLI） |
| `qchem` | `qchem-run` / `qchem-export-parity`，CLI 不在则本地回退 |
| `ionstack` | `GET /v1/twin/identity`、`POST /v1/twin/run`（`QAGENT_TWIN_URL`） |
| `route` | 同一 `ionstack_compile_estimate`，`QAGENT_ROUTE_BACKEND` |
| `qiskit` | pin + Aer 合同；不 import qiskit |
| `docs` / `codex` | 栈内手册 / algo SPI 缝 |

加第四家软件：`qagent/contracts/engines/HOW_TO_ADD.md`。
