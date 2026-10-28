# P4 批次 A1 执行记录：G2 窄链重验与平台接缝登记（2026-10-26）

依据：[约 2000 人天计划](company-agent-2000-person-days-development-plan-v1.0.zh-CN.md) P4「量子、云平台和 HPC 作业适配」；冻结任务集 [TS-1](task-set/ts1-narrow-chain.json)（P0 阶段冻结于本日 11:30）。本批次是 P4 的**接缝核验批次**：在 P1（主体/租户）、P2（门户/蒸馏器）、P3（网页抓取/预算/数据定型/文件引用）各批次全部落地之后，把冻结的七任务七反例窄链**逐门重新跑一遍**，然后才允许平适配继续。不改产品代码、不改合同。

## 1. 重验结果（全部通过）

证据 [ts1-recert-2026-10-26/recertification.json](evidence/ts1-recert-2026-10-26/recertification.json)：

- T1–T4 + C3/C4/C6：`tests/test_platform_compatibility.py -m platform_compatibility`（真实公司平台适配器，`COMPANY_AGENT_PLATFORM_SOURCE=`）→ **1 passed**。
- T5（冻结后等价门改名）：shots 下界/上界在派发前拒绝 + `tests/test_providers.py`（含模拟器不能伪造/隐藏 twin_id）→ **62 passed**。
- T6：`tests/test_hpc.py` → **101 passed**，与冻结日数量一致（slurm_number/job_name 绑定 business_ref 语义未漂移）。
- T7 / C7 / C5 / C1：**3 + 1 + 2 passed**。
- C2：合规门禁当时点 **22/22 ok**（`compliance-local.json`，含并行门户批次的场景自适应）。

## 2. 接缝登记（P4 剩余与 Owner 依赖）

内核已交付的 P4 面：QASM 内容限制 + 降级器（`cloud.read_program`：无 symlink、64KB、TOCTOU 指纹、`OPENQASM 3` 版本头、include 白名单）、云/HPC/真机受 provider 合同与审批链、事件丢失 → unknown、`request_id` 非幂等键、平台侧的业务引用绑定。

**剩余 Holy 面全部依赖平台 Owner 或真实窗口，不在内核侧发明**：

1. 平台事实源的事件游标与重复事件去重语义（`receipts.reconcile` 已按平台事实闭环，但响应丢失/重复上报的去重判定必须由真实事件流给出）。
2. 上传 QASM 的平台侧 `circuit_id` 资产登记（内核已在提交前完成内容哈希与预算，登记事实现属平台）。
3. 云取消的平台语义（DSH abort → unknown 已闭环，平台终态对账待 Owner）。
4. HPC 结果资产提升（slurm_number/job_name 绑定已有，结果资产化等待平台）。
5. 受监督真机窗口（`quantum_device_run` 已具备 lab/sign 人工审批链，真实 provider 窗口按计划 P4 前后推动）。

按计划「不新增模型循环/工具循环，平台状态以平台事实为准」执行登记。

## 3. 测试与门禁（不含全量）

- 逐门命令与结果见证据 JSON（合计 7/7 绿）；未跑全量 pytest（按工作方式约束）。
- 后续批次（P5-a1）在同一门禁集上继续，不再重复本记录。
