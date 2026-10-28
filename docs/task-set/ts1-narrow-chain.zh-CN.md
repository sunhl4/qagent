# 任务集 TS-1：窄链验收任务与反例（G0→G2 冻结件）

版本：1.0.0；冻结：2026-10-26T11:30+08:00（对应 [P0 执行记录](../company-agent-plan-p0-2026-10-26.zh-CN.md) 第 3 节能力清单第 1–6 项）。冻结后修改任何一行都会改变摘要，需按变更流程重新登记。

## 机器可读与摘要

- 清单：`docs/task-set/ts1-narrow-chain.json`
- **任务集摘要（验收四元组第 4 项）**：`sha256:b480c84c6671c5585e02502620299c749860ddb82ed91bb61badb7e91821df5d`（2026-10-26 冻结并全部门禁实测后计算；复算方式见文件尾部）
- **合同 digest（四元组第 2 项）**：`sha256:49a775cf1bc202e22776d7d8b69904edbddf449d232b7a9649e72a21da2e113a`（2026-10-26 实测；冻结时点为 `sha256:4129a4b6…`，随回执合同 1.2 更新）
- **DSH/组件版本（四元组第 1 项）**：`0.1.5-rc.2`
- **本地模型标识与版本（四元组第 3 项）**：待模型 Owner 登记——探针 `scripts/probe_model_service.py` 的证据按请求记录 `model` 字段（本轮核对源码确认），登记后即可满足四元组要求，无需改探针代码。

## 通过标准与不变量

每一条任务 (T) 必须通过其门禁、每一条反例 (C) 必须被拒绝并留下证据；任何一行失败即阻塞 G2。全部行禁止：新第二 Runtime、越句柄三类（`asset_id` / `circuit_id` / `twin_id`）、设备自动重试、未知状态当作终态。

## 任务（正向链路）

| ID | 任务 | 验证门禁 | 通过标准 |
| --- | --- | --- | --- |
| T1 | 目录发现与 `component_id`、游标分页 | `pytest tests/test_platform_compatibility.py -m platform_compatibility` | 可运行条目返回 id/version/runnable=true；query 漂移被拒 |
| T2 | 受控 `algorithm.run` 返回 `asset_id`+`circuit_id` | `pytest tests/test_platform_compatibility.py -m platform_compatibility` | 指标符合 `scientific-metrics/1.0`；无正文泄漏 |
| T3 | `asset.get` / `asset.metrics` 按句柄取数 | `pytest tests/test_platform_compatibility.py -m platform_compatibility` | 快照与运行一致；跨租户报错 |
| T4 | `metric-summary` 模板消费拉取的表 | `pytest tests/test_platform_compatibility.py -m platform_compatibility` | audit 状态 complete；结构违例失败闭合 |
| T5 | `quantum_simulate` QASM 边界与 shots 上限 | `pytest tests/test_invoke.py -k simulate` | 使用 `circuit_id` 句柄；越界拒绝 |
| T6 | HPC `submit → job-status → file-fetch` 链 | `pytest tests/test_hpc.py`（冻结日 101 passed） | `slurm_number/job_name` 成功时绑定 `business_ref` |
| T7 | 回执交付业务引用 | `pytest tests/test_receipts.py -k business_ref` | 仅 ok+completed 绑定；reconcile 可见 |

## 反例（必须被拒绝）

| ID | 反例 | 验证门禁 | 期望 |
| --- | --- | --- | --- |
| C1 | 模拟器不能铸造/隐藏 `twin_id` | `test_providers.py::test_simulator_cannot_mint_twin_id`、`..._cannot_hide_nested_twin_id` | denied |
| C2 | 设备 boot/algo 拒绝；未知工具拒绝 | `scripts/compliance_gate.py`（boot/algo deny、unknown tool 场景） | denied，`not_dispatched` |
| C3 | `component_version` / `catalog_version` / 参数漂移 | `test_platform_compatibility.py`（四个 patch 分支） | 派发前 error |
| C4 | 跨租户资产访问（owner-b 令牌访问 owner-a 资产） | `test_platform_compatibility.py` | error，无数据 |
| C5 | 未确认派发进入 unknown 直到对账 | `test_receipts.py::test_unconfirmed_dispatch_only_is_flagged_as_unknown` | 仅平台事实消除旗标 |
| C6 | 无效令牌与坏信封失败闭合 | `tests/test_providers.py -k envelope`；兼容门禁 `invalid-synthetic-token` 分支 | error，零外发 |
| C7 | `business_ref` 不在非成功结局绑定 | `test_receipts.py::test_business_ref_never_binds_outside_a_binding_success` | ref 为空 |

## 2026-10-26 门禁实测（冻结依据）

- `tests/test_platform_compatibility.py`（双仓，平台适配器 + inert 执行器）：**1 passed**。
- QASM / 句柄 / 回执定向子集（test_invoke、test_cloud 与回执四用例、模拟器 twin 反例）：**78 passed**。
- `tests/test_hpc.py`：**101 passed**（T6 / C5 相关链路依据）。
- 全量 pytest：**871 passed / 2 deselected**；`scripts/compliance_gate.py`：**13/13 ok**。
- 边界：全部在假平台替身（fixture owner-a / owner-b 令牌对）上；到真实端点的升级 = 相同门禁接到 Owner 提供的接口，fixture 降级为回退证据。

## 摘要复算

```bash
python3 - <<'PY'
import hashlib, json
raw = open('docs/task-set/ts1-narrow-chain.json','rb').read()
canon = json.dumps(json.loads(raw), ensure_ascii=False, sort_keys=True).encode()
print(hashlib.sha256(canon).hexdigest())
PY
```

## 范围与变更规程

不含真实租户目录、无人值守设备运行、`company.latex` pull/push 流程、多云端点并行。修改任务或反例集合：改 JSON → 重跑全部关联门禁 → 重算摘要 → 在本文与 P0 执行记录登记新摘要与冻结日期。
