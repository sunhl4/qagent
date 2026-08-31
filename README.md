# Qagent · 公司科研 Agent

合肥市幺正量子科技有限公司的办公 / 科研 Agent。人在设置里接上**自己的本地大模型**，然后用自然语言做事。它是普通 Agent，同时已经接上公司软件包：量子化学、量子数据、线路优化、编译估计、模拟器、知识库；超算和量子计算机账户在设置里填。加开源包只登记，不新写 agent。上机仍要人批，没有 `twin_id` 不能像签收。运行时仍是 dsh + Codex，不要另写一套 harness。

本仓从 `Q-data` 抽出：预研数据 / 配置 / 复现脚本仍在 https://github.com/sunhl4/Q-data 。科学核 `qdata` 是另一个仓库，本仓只经 CLI / HTTP / 合同 store 接线，禁止 `import qdata`。

## 引擎包

| 包 | 接线 | 句柄 |
|----|------|------|
| `qdata` | CLI / HTTP / 合同 store（禁 mkdtemp） | `asset_id` · B3 |
| `qchem` | `qchem-run` CLI | `asset_id` · `circuit_id` |
| `ionstack` | TwinRun REST | **唯** `twin_id` |
| `route` | 同一 `compile_estimate` | `makespan_ns` |
| `qiskit` | pin + Aer | **禁** `twin_id` |

黄金路径：`qchem/qdata → pin → 可选 Aer → compile_estimate → TwinRun(ask) → B3`

开机时把下面这段交给 Agent（不要粘贴密钥）：

> 先读 `AGENTS.md`、`handbooks/orange-book.md`、`INTERFACES.md`。按造包 / 评测 / 上机三条路由走。句柄只有 circuit_id / asset_id / twin_id。boot 与 qagent-minimal 里不能出现 Twin 工具。凭证只让我填进 ignored 文件，不要把完整密钥读进对话。

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python tests/run_tests.py
PYTHONPATH=src python -m qagent.entrypoints.eval_cli
PYTHONPATH=src python -m qagent.entrypoints.doctor_cli
```

人入口：

```bash
cd /Users/shl/nvidia/qagent
bash scripts/start_ui.sh
# http://127.0.0.1:3080
```

写算法需要完整对话时再开 runtime：`bash scripts/start_runtime.sh`（`:3081`）。活科学：`export QAGENT_IONSTACK_HOME=...` 后 `bash scripts/start_twin.sh`；`export QAGENT_QDATA_HOME=...` 后 `bash scripts/start_qdata.sh`。

回执核验（不依赖 Qagent 包）：

```bash
python3 scripts/verify_receipt.py receipt.json
```
