# 公司算法 / 软件目录

公司算法目录。克隆本仓即可列出。卡片在 `contracts/hub/catalog_face.json`，不必本机安装 algo-hub、qdata、qchem 或 ionstack。活 `run` 仍要幺正托管的 HTTP。

问「有哪些算法」「公司软件」「VQE」「QAOA」走 `qagent_hub_list` / `qagent_hub_describe`。选型不合并：有分子走 `org.chem.vqe`，已有 Pauli 走 `org.algo.vqe.hea`。

## 化学求解（qchem-stack）

| id | 用途 |
|----|------|
| `org.chem.vqe` | 分子基态，固定深度 HEA/UCC |
| `org.chem.adapt` | 费米子池自适应 ansatz |
| `org.chem.tetris_adapt` | 并行算符打包的 ADAPT |
| `org.chem.iqeb` | 量子比特激发外环 + 内层 VQE |
| `org.chem.sa_vqe` | 态平均，一次变分多态 |
| `org.chem.gqe` | 生成式本征求解（研究） |
| `org.chem.qpe` | 相位估计族（研究） |
| `org.chem.sqd` | 采样后再经典子空间对角化（QSCI / SQD） |
| `org.chem.embed.dmet` | 碎片嵌入工作流，宿主仍是 VQE |
| `org.chem.excited.vqd` | 基态后的 VQD 激发态 sidecar |
| `org.chem.excited.qse` | 量子子空间展开 sidecar |
| `org.chem.excited.sceom` | SCEOM sidecar |

`org.software.qchem-stack` 是化学管线软件面，不是可选求解器。

## 离子阱求解（uqc_algorithm）

| id | 用途 |
|----|------|
| `org.algo.vqe.hea` | 已有 Pauli / SparsePauliOp，无分子 SCF |
| `org.algo.qaoa.maxcut` | 组合优化 / MaxCut |
| `org.algo.qrc.mnist` | 储备池分类演示 |
| `org.algo.trotter.first_order` | Trotter 线路辅助，不是独立求解器 |

`org.software.uqc-algorithm` 是离子阱算法库软件面，不是可选求解器。

## 运行时 / 编译 / 演示

| id | 用途 |
|----|------|
| `org.runtime.qiskit-uqc-sim` | 本地离子阱风格 Qiskit backend |
| `org.runtime.uqc-cloud` | 公司云上机（一条逻辑运行时） |
| `org.runtime.iontrap-noise` | Aer 上的离子阱噪声注入 |
| `org.compiler.h2` | QASM → 离子阱日程；换 `compile_estimate` 后端 |
| `org.workflow.qccd` | QV / GHZ / RCS 基准流水 |
| `org.demo.uqcdemo` | 教学 SDK，不要当成 `run(algorithm_id)` |

核验（任意机器，无需本机科学核）：

```bash
PYTHONPATH=src python3 -c "from qagent.adapters.hub import NativeHub; print(NativeHub().list_assets({}))"
```
