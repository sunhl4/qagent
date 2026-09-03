# Qagent · 公司科研 Agent

合肥市幺正量子科技有限公司的办公 / 科研 Agent。人在设置里接上**自己的本地大模型**，然后用自然语言做事。它是普通 Agent，同时已经接上公司软件包：量子化学、量子数据、线路优化、编译估计、模拟器、知识库；超算和量子计算机账户在设置里填。加开源包只登记，不新写 agent。上机仍要人批，没有 `twin_id` 不能像签收。运行时仍是 dsh + Codex，不要另写一套 harness。

本仓从 `Q-data` 抽出：预研数据 / 配置 / 复现脚本仍在 https://github.com/sunhl4/Q-data 。科学核 `qdata` 是另一个仓库，本仓只经 CLI / HTTP / 合同 store 接线，禁止 `import qdata`。

## 引擎包

| 包 | 接线 | 句柄 |
|----|------|------|
| `qdata` | CLI / HTTP / 合同 store（禁 mkdtemp） | `asset_id` · B3 |
| `qchem` | HTTP（`QAGENT_QCHEM_URL`）或 `qchem-run` CLI | `asset_id` · `circuit_id` |
| `ionstack` | TwinRun REST | **唯** `twin_id` |
| `route` | 同一 `compile_estimate` | `makespan_ns` |
| `qiskit` | pin + Aer | **禁** `twin_id` |

黄金路径：`qchem/qdata → pin → 可选 Aer → compile_estimate → TwinRun(ask) → B3`

开机时把下面这段交给 Agent（不要粘贴密钥）：

> 先读 `AGENTS.md`、`handbooks/orange-book.md`、`INTERFACES.md`。按造包 / 评测 / 上机三条路由走。句柄只有 circuit_id / asset_id / twin_id。boot 与 qagent-minimal 里不能出现 Twin 工具。凭证只让我填进 ignored 文件，不要把完整密钥读进对话。

别人只要 GitHub 链接，不必碰到作者本机目录：

```bash
git clone https://github.com/sunhl4/qagent.git
cd qagent
PYTHONPATH=src python3 tests/run_tests.py
PYTHONPATH=src python3 -m qagent.entrypoints.eval_cli
PYTHONPATH=src python3 -m qagent.entrypoints.doctor_cli
PYTHONPATH=src python3 -c "from qagent.adapters.hub import NativeHub; print(NativeHub().list_assets({}))"
PYTHONPATH=src python3 -m qagent.entrypoints.shell_cli --serve --host 127.0.0.1 --port 3080
# 或：bash scripts/start_ui.sh
# http://127.0.0.1:3080
```

克隆即可：打开 3080、列出已接引擎、读仓内 **24** 张公司算法/软件卡片（`contracts/hub/catalog_face.json`）、检索 `handbooks/` 与 `knowledge/`。不必本机安装 algo-hub / qdata / qchem / ionstack，也不要把 `QAGENT_ALGO_HUB_HOME` 指到别人电脑上不存在的路径。活计算要幺正托管的 HTTP（设置里的软件包 URL，或环境变量 `QAGENT_QDATA_URL` / `QAGENT_QCHEM_URL` / `QAGENT_TWIN_URL` / `QAGENT_ALGO_HUB_URL`），再接模型并启动 `bash scripts/start_runtime.sh`（`:3081`，不要当官网）。空 URL 不是本机 `:8787` / `:8765`。合同见 `contracts/cloud/company.json`。

官网：只反代 3080。dsh 与科学核留在幺正内网。组内调试仍可用本机 `*_HOME` + `scripts/start_twin.sh` / `start_qdata.sh`。

回执核验（不依赖 Qagent 包）：

```bash
python3 scripts/verify_receipt.py receipt.json
```
