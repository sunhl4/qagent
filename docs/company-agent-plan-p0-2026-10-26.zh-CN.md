# P0 执行记录与首版范围冻结：2026-10-26

状态：[约 2000 人天计划](company-agent-2000-person-days-development-plan-v1.0.zh-CN.md) 的 P0 已启动。本轮按计划边界只做只读清点、回归修复和范围冻结；未连接真实模型/云/HPC/QPU，未读取凭据，未改动 `contracts/`、`src/` 业务逻辑。需公司侧提供的输入见第七节。

## 1. 事实基线（本轮读到的现状）

版本与协议（`pins.json`）：DSH `0.1.5-rc.2`、Codex 子pkg `0.1.5-rc.2`、官方 Codex `0.153.4`、node `22.22.0`、pnpm `12.5.1`、provider 协议 `company-agent-provider/1.0`。

Provider 身份：`contracts/providers.json` 平台 provider `id="uniqon"`；Uniqon 侧 `src/uniqon/adapters/company_agent_provider.py:36` 声明 `PROVIDER = "uniqon"`。**两侧身份一致**，此前文档记录的 `company-quantum-platform` 漂移已在平台侧解决。遗留项：env 变量名仍为 `COMPANY_QUANTUM_PLATFORM_INVOKE_URL/TOKEN`（仅命名遗留，无行为影响，登记为低风险清理项）。

合同规模：

- 8 份合同：capabilities / policy / presets / providers / results / skills / templates / tools。
- 40 个工具；10 个能力：`company.algorithm`(2 工具, uniqon)、`company.asset`(4, uniqon)、`quantum.simulation`(1, independent-simulator)、`quantum.compilation`(1, independent-compiler)、`quantum.device`(2, ionstack-twinrun)、`compute.cloud`(4, uqc-cloud)、`compute.hpc`(11, hpc-slurm-ssh)、`company.knowledge`(1, local)、`company.workflow`(3, local)、`company.latex`(11, local document)。
- 4 个 preset 可见工具：`lab`=40、`algo`=23、`sign`=16、`boot`=4；设备 ask 仅 `lab/sign`，deny 为 `boot/algo`（`contracts/policy.json`，`tests/test_policy.py` 门禁）。
- 4 个注册 Skills：company-knowledge、company-docs-research、company-software-development（profile×preset `when` 受控）、quantum-workflow（仅 `company-agent` profile 的 `lab/sign`）。

## 2. 回归基线复验与修复

进入 P0 前全量 `pytest` 出现 **4 项失败（867 通过）**；修复后 **871 通过 / 2 deselected**（约 3.5 分钟），`scripts/compliance_gate.py` **13/13 绿**，证据已更新至 `docs/evidence/compliance-local.json`。

修复内容（全部为测试钉与最新合同脱节，非业务缺陷；遵循"合同先变、测试同步"的顺序惯例）：

1. `tests/test_installed_wheel.py:33`：wheel 内工具断言 `29 1 → 40 1`（LaTeX 工具批次把合同扩到 40）。
2. `tests/test_installed_wheel.py:59`：capability 数 `9 → 10`（新增 `company.latex` 后第 10 个能力）。
3. `tests/test_receipts.py:416`：lab 预设 ask 批准清单补入 `company_latex_batch_edit / company_latex_edit / company_latex_push / company_latex_revert`（与 `invoke.py` 中"可见工具×decide==ask"的运行时事实一致）。

流程规则（新增到工程治理）：**任何能力/合同批次合并前，必须在本机跑全量 pytest 与合规门禁**；本轮的 3 处脱节说明只按"实现文档钳位清单"局部更新的做法会漏钉。

## 3. 首期有界能力目录（G0 冻结件）

首版可验收的能力集合 = 上述 10 个能力，不新增第三类 provider 类型。第一批窄链只启用：

1. `quantum.simulation`（一个模拟器，本地假平台替身先行）。
2. `compute.hpc`（一个 SLURM 流程：`hpc.submit → hpc.job-status → hpc.file-fetch → 结果资产`）。
3. `company.algorithm`（`algorithm.catalog` 发现 + `component_id` 映射；`algorithm.run` 的受控执行进窄链）。
4. `company.asset` 之 `asset.metrics`（指标快照→模板）。
5. `company.knowledge` / `company.workflow`（已落地治理）。
6. 受监督 `quantum.device`（仅 lab/sign ask；首版只走一个 provider 一个审批流）。

暂缓进入首版验收：`company.latex` 的 `pull/push`（会改动外部文档库的 ask 工具）与 batch 编辑流程、`quantum.compilation` 仅作为辅助阶段、多家云端点并行。此清单与计划第八节"范围收缩序"一致：收缩时先冻结本节 1–6，不动安全门槛。

## 4. 内外账户边界（P1 的验收起点）

当前事实层：preset 即能力边界（`lab` 内部开发、`algo` 内部自动、`sign` 对外、`boot` 受限通用）；知识 registry 已按 `public/internal` 受众过滤且 `sign` 只看 public。企业逐用户开通/租户授权尚未实现——`apps/company-workspace/host.mjs` 的演示级全局开通状态只能到演示范围。P1（200 人天）的交付就是把这个演示状态升级为逐用户：由公司身份源出主体，Agent 只投影与执行前核验。

## 5. 验收四元组模板（自下批验收报告起强制）

- DSH/组件版本：`pins.json` 当前 `0.1.5-rc.2`。
- 公司合同 digest：`sha256:49a775cf1bc202e22776d7d8b69904edbddf449d232b7a9649e72a21da2e113a`（2026-10-26 起，随回执合同 1.2 与主体来源合同更新；此前为 `sha256:4129a4b6…`）。
- 本地模型标识与版本：**待模型 Owner 登记**（探针 `scripts/probe_model_service.py` 证据已绑定端点行为，缺版本标识字段时不得作为对比证据）。
- 任务集标识：已冻结为 **TS-1**（[清单与门禁映射](task-set/ts1-narrow-chain.zh-CN.md)；摘要 `sha256:b480c84c6671c5585e02502620299c749860ddb82ed91bb61badb7e91821df5d`，2026-10-26）。修改任务集须重算摘要并重新登记。

## 6. 风险登记（对 260 人天储备的门控）

| 编号 | 风险 | 触发证据 | 应对与储备挂钩 |
| --- | --- | --- | --- |
| R1 | 能力批次与门禁钉脱节 | 本轮 3 处测试钉修复 | 合并前全量回归规则（第 2 节）；不单独扣储备 |
| R2 | 平台 Agent 接口/委托与现状不符 | 待平台 Owner 首批 API 合同 | 储备 100 人天后备 |
| R3 | 本地模型协议/容量差异 | 待模型版本登记与探针复测 | 储备 40 人天后备 |
| R4 | 设备窗口/数据缺陷 | 待 QPU 审批人与窗口 | 储备 40 人天后备 |
| R5 | 租户与外发整改 | P1 双租户验收 | 储备 60 人天后备 |
| R6 | env 命名遗留 `COMPANY_QUANTUM_PLATFORM_*` | 本轮清点 | 低风险，并入某批合同小版本清理 |

## 7. 十日窄链清单（含责任归属）

| 项 | 内容 | 责任 | 状态 |
| --- | --- | --- | --- |
| 1 | provider 身份与版本冻结 | 工程侧 | 已完成（本轮事实基线第 1 节） |
| 2 | 全量回归与合规门禁绿 | 工程侧 | 已完成（871 通过、13/13） |
| 3 | 云平台 API 合同（状态枚举/事件游标/取消语义/业务作业号） | **云平台 Owner** | 待输入 |
| 4 | HPC API 与测试租户（SLURM 提交/状态/取数） | **HPC Owner** | 待输入 |
| 5 | 本地模型标识、端点协议、tool-call/SSE 说明 | **模型 Owner** | 待输入 |
| 6 | 两个隔离租户 + 一个模拟器 + 一次 QASM + 一次拒绝 + 一次 unknown 恢复（假平台替身） | 工程侧 | 已完成（假平台替身，2026-10-26，见第 9 节；真实租户待输入） |
| 7 | QPU 审批人与测试窗口指定 | **设备 Owner** | 待输入 |
| 8 | 账单映射 Owner 与字段样例 | **财务/平台** | 待输入 |

工程侧可先行项与"待输入"项分列，只要有任一待输入在 10 个工作日内未到位，即按计划第十一节释放对应储备或收缩范围；不影响第 6 项的本地完成度。

## 8. 本轮验证记录

- `python3 -m pytest -q`：修复前 4 failed / 867 passed；修复后 **871 passed / 2 deselected**（两次全量）。
- `python3 scripts/compliance_gate.py`：**13/13 ok**，输出 `docs/evidence/compliance-local.json`（2026-10-26 11:19 重生成）。
- 读到的合同与能力计数见第 1 节；Uniqon 身份对齐见第 1 节。
- 未运行任何真实服务；未改 `contracts/`；测试钉修改共 3 处。

## 9. 复核与窄链先行执行记录（2026-10-26 上午续批）

对本文完成一次复核，修正 3 处不准确表述（`company.latex` 工具清单按实际 `pull/push` 写、`algorithm.run` 表述改为受控执行、两处笔误）；`tests/test_receipts.py:416` 行号与证据文件时间戳核实无误。

十日清单第 6 项的本地先行执行（全部为假平台替身，未触达真实服务）：

1. **双租户与未知拒绝链（双仓兼容门禁，真实平台适配器 + inert 执行器）**：`COMPANY_AGENT_PLATFORM_SOURCE=/home/sunhl/projects/company-quantum-platform python3 -m pytest tests/test_platform_compatibility.py -m platform_compatibility` — **1 passed**。覆盖：目录发现与游标分页、`component_version/catalog_version` 漂移拒绝、参数越界与未知字段拒绝、`algorithm.run` 返回 `asset_id/circuit_id`、`asset.get/metrics`/模板链、owner-b 令牌对 owner-a 资产 401 式拒绝、无效令牌拒绝、资产持久化并跨进程重开一致。
2. **QASM 边界、句柄防伪与不确定恢复（78 项定向回归）**：`python3 -m pytest tests/test_invoke.py tests/test_cloud.py <receipts 四用例> <simulator twin_id 两反例>` — **78 passed**。覆盖：`quantum_simulate` shots 边界、模拟器不能铸造/隐藏 `twin_id`、跨 asset 提交拒绝、回执 `business_ref` 只允许成功结果绑定、未确认派发进入 unknown 对账。

诚实边界：这里的"两个租户"是平台适配器 fixture 的 owner-a/owner-b 令牌对，验证的是**权限与对账语义**；真实租户目录、真实云/HPC/QPU 接入仍属第 3/4/5/7/8 项的待输入范围。第 6 项对真实平台的升级对照即这些门禁测试本身的迁移。

