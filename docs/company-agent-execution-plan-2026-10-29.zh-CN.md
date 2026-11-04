# Company Agent 剩余工程执行计划（2026-10-29）

本文件是 `company-agent-2000-person-days-development-plan-v1.0.zh-CN.md` 的执行附录，不改变 2000 人天基线、DSH（DeepSeek Harness，唯一 Agent Runtime）边界、合同先行顺序或风险储备释放规则。全公司三个面的扩展顺序见 `docs/super-dsh-product-plan.zh-CN.md`。

## 一、当前基线

截至 2026-10-29，工程侧已完成 P0，P1 的主体与租户合同批次，P3 的网页抓取、预算、数据与文件引用收口，P4-A1 窄链重验，P5 的模板与知识撤权门禁，以及 P8 的治理和许可批次。2026-10-28 至 2026-10-29 的 Office/WPS 适配已覆盖摄取、创建、比较、编辑、校验、图表、事项、格式体检、PPTX、转换、打开、计算沙箱和交付命名。

本轮开始前的硬门禁缺口是：

- 临时 `wsl_pnpm_setup.sh` 留在根目录，触发无遗留目录检查。
- 两个 profile 的 Office 依赖锁文件需要用冻结安装复验。
- P6 只有资源页、只读回执和连接状态投影，缺少独立的服务端工作台任务投影。
- P8 已有网页注入信号检测，但还没有把“检测结果不改变授权、不触发工具”的反例纳入持续门禁。
- P7、P9 尚未启动；真实云/HPC/QPU、企业身份、账单字段和模型版本仍等待 Owner 输入。

## 二、执行原则

1. 先关闭当前工作区卫生和 profile 可复现性问题，再进入新批次。
2. P6 先做只读服务端事实投影，不新增模型可见工具、不新增会话循环、不把前端事件当作平台终态。
3. P8 先做离线可重复的网页注入隔离门禁；网页正文永远是 `untrusted_reference_data`（不可信引用数据），信号只用于标记和验收，不授予任何权限。
4. P4 的真实平台接入、P7 的计费对账和 P1 的企业身份接线，在 Owner 输入到位前只做合同、模拟器和失败闭合，不伪造生产完成。
5. 每个批次必须同时提交：实现记录、定向测试、全量或明确范围的门禁结果、未完成边界和风险变化。

## 三、已执行的 E0：工作区收尾

状态：已完成。

- 删除未被工程引用的根目录临时脚本 `wsl_pnpm_setup.sh`。
- 使用 `corepack pnpm` 对 `profiles/company-agent` 和 `profiles/company-agent-minimal` 执行 `install --frozen-lockfile --ignore-scripts`。
- 运行 `tests/test_no_legacy.py tests/test_verify_dsh_profiles.py`：20 项通过，1 项按既有标记排除。
- 该批次不改变合同、Python adapter、DSH 插件或生产策略。

出口证据：冻结锁文件安装日志、无遗留门禁结果和本文件的执行记录。

## 四、E1：P6-A 服务端工作台任务投影

目标：让网页端和本地端从同一个服务端只读事实源查询受理任务，即使右栏会话断开，任务仍可在工作台查询。

### 实现范围

- 在 `apps/company-workspace/host.mjs` 增加 `/company-workspace/workbench/tasks` 只读端点。
- 端点只读取既有 `company-agent reconcile` 回执，按 `request_id` 折叠 dispatch/outcome 记录，不创建新任务、不重试外部作业。
- 只投影 `cloud.submit`、`hpc.submit`、`device.run` 三类绑定作业；忽略普通对话和非作业记录。
- 每行只包含受控字段：`request_id`、`operation`、`status`、`execution_state`、`business_ref`、`result_state`、`billing_state`、`updated_at` 和 `source`。
- `unknown` 必须保持 `unknown`；没有平台业务引用时不能显示为已完成。`billing_state` 在 P7 未完成前固定为 `not_projected`，不冒充计费事实。
- 在现有资源中心首页显示任务列表；刷新通过服务端端点完成，提交、取消和审批仍只能在 DSH 对话工具中进行。

### 测试与出口

- Node UI 测试验证：回执折叠、未知状态保留、业务引用只来自成功结果、非法字段丢弃、服务端不可用时不伪造任务。
- 运行 `node --test tests/ui/shell-host.test.mjs`。
- 运行 `python -m pytest tests/test_no_legacy.py tests/test_verify_dsh_profiles.py tests/test_receipts.py -q`。
- 出口条件：两个客户端读取同一端点；关闭右栏会话后刷新仍能看到任务；没有任何自动重投或前端伪造终态。

## 五、E2：P8-A 网页内容注入隔离门禁

目标：把 H40 反例固化为持续门禁：网页中的“忽略指令”“调用工具”“泄露凭据”和“改变身份”文本只能成为不可信数据和信号，不能改变授权决策或触发 Agent 工具。

### 实现范围

- 在 `tests/test_web_fetch.py` 增加端到端反例：页面返回注入文本时，结果仍带 `trust=untrusted_reference_data` 和分类信号。
- 同一输入不得改变 `decide()` 对设备、计划写入和 HPC 写入工具的结果；页面内容不得出现在授权参数、审批上下文或回执 dispatch 记录中。
- 在 `scripts/compliance_gate.py` 增加一个离线场景，使用本地回环 HTTP 服务或直接的信号结果验证“检测、标记、不授权”三件事。
- 保持大页面和扫描不完整时的 `scan.complete=false`；不把启发式信号报告写成安全判定。

### 测试与出口

- 运行 `python -m pytest tests/test_web_fetch.py -q`。
- 运行 `python scripts/compliance_gate.py`，合规场景必须全部通过。
- 出口条件：注入文本不会把 `company_plan_issue_create`、`hpc_submit` 或 `quantum_device_run` 从 deny/ask 变成 allow；不会产生 provider dispatch 或设备回执。

## 六、后续批次顺序

### E3：P6-B 工作台状态轴与断线恢复

状态：已完成本地 focused implementation；真实多客户端/平台订阅验收仍未完成。

- 服务端任务投影分离执行、结果、审批、连接和计费状态。
- 重复/乱序/旧事件/非法状态组合 fail closed；无业务引用不得显示 completed。
- 可信主体绑定回执子进程和缓存键；断线快照只恢复为 reconnecting，不推断取消或完成。
- 证据：`docs/implementation-2026-11-02-e3-e4.zh-CN.md`，Node 13/13，Python focused 51 passed/1 skipped。

### E4：P8-B 多租户和撤权反例扩展

状态：已完成本地 focused implementation；真实企业 IdP 和生产双租户验收仍等待 Owner。

- 回执、reconcile、工作台任务投影和宿主缓存使用服务端可信主体隔离。
- 撤权、过期、坏 registry、不可信主体和跨主体读取保持失败闭合。
- 证据：`docs/implementation-2026-11-02-e3-e4.zh-CN.md`，跨主体 fixture 与 UI 主体/缓存反例通过。

### E5：P2/MCP 与模型验收收尾

等待模型 Owner 提供版本标识和协议说明后执行。分别验证 HTTP 和 STDIO 传输、工具调用、SSE、结构化输出、上下文裁剪保留审批依据、异常时不切换未批准外部模型。

### E6：P4 真实平台接缝

等待云平台 Owner、HPC Owner 和设备 Owner 提供状态枚举、事件游标、取消语义、测试租户和 QPU 窗口。优先一个模拟器、一个 HPC 流程和一个人工 ask 真机流程；未知状态只对账，不重投。

### E7：P7 计费与运营

等待财务/平台提供字段样例后，分别建立模型 token、HPC 节点时、QPU 用量和企业账单引用的对账规则。观测 trace 只作诊断，不作为账本或合规凭证。

### E8：P9 试点与交接

在 G1–G4 通过后执行。至少一个内部租户和一个外部租户完成代表性任务；发布可回滚；版本钉、合同摘要、任务集、验收证据、运行手册和支持升级路径齐全。

## 七、当前依赖和风险门控

- 云平台 API、HPC API、模型版本、QPU 审批窗口、账单字段和企业身份仍是外部输入，不以本地测试替代。
- 260 人天储备只有在接口不一致、安全整改、模型协议差异、真实设备窗口或试点缺陷出现并登记证据后释放。
- 若 Owner 输入继续缺失，首版范围保留身份、租户、审批、模拟器、HPC、结果完整性和失败闭合；先缩减多 QPU、自动记忆、更多第三方工具和复杂 UI，不降低安全门槛。

## 八、执行记录格式

每个后续批次必须在 `docs/` 增加 `implementation-YYYY-MM-DD-<slice>.zh-CN.md`，至少写明：计划映射、合同是否变化、适配器和插件变化、测试命令及数量、门禁证据、真实平台边界、未完成项和下一批依赖。机器可读状态同步到 `company-agent-2000-person-days-development-plan-v1.0.json` 的 `executed_batches` 或 `planned_batches`。
