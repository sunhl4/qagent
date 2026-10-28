# oss-survey P1/P2 落地实现（2026-10-23）

按 `docs/oss-survey/04-工程衔接建议.zh-CN.md` 完成 P1 全部四项与 P2 两项，遵循开发顺序：合同 → Python adapter → DSH 插件 → 测试。回归基线：pytest 全量 **827 通过 / 0 失败**；UI node 套件（tests/ui）**24 通过 / 0 失败**；P0 批次（见 implementation-2026-10-22-oss-survey-p0）全部保留。本批不新增任何模型/会话/工具循环，不开放绕审批 shell 路径，硬规则不变。

## 1. P1-3.1 分析模板（`company_analysis_render`）

- 合同：新增 `contracts/templates.json`（两个受管模板：`metric-summary`、`shots-audit`；每个都声明输入来源、schema 版本、错误行为、输出形状）；`contracts/tools.json` 新增工具（`company.workflow` 能力，参数/输出 schema：受管 reason 词汇表、图表为声明式 bar 化指标、无自由文本插槽）；`capabilities.json`、`presets.json` 同步（四个 preset 全部可见——本地纯判定，无外发）。
- 适配器：`src/company_agent/analysis.py`。结构错误（未知模板、无 metrics 表、schema 版本不匹配、shots 记录缺失/非法）**fail-closed**；域级违例（概率越界、count 单位耦合、重复名、空表、超投/欠投）**flagged**——诚实上报且**不渲染图表**，防误导；输出经 `validate_output_content` 参考，绝不携带 QASM/bitstring/密钥/脚本/URL/路径形状内容。
- 命名：输出键为 `audit`（治理卷冢单），与 provider 结果的 `summary`（duration_ms/metrics 科学家族）语义分离，`test_contract_upgrade` 的 summary 家族门禁含义不变。
- DSH 插件：零代码改动——由合同驱动的 `company-agent-core` 注册（company.workflow）自动生效。

## 2. P1-3.2 知识入库治理（`knowledge/registry.json`）

- 每个 knowledge 根可用 `registry.json` 登记条目：`{file, sha256, audience: public|internal, approved, revoked, expires_epoch}`；坏注册表 → 该根跳过（`registry_invalid` reason，fail-closed，绝不全体放行）；缺注册表的根保持遗留行为（测试夹具走 tmp 根不受影响），builtin 工作区根的注册表随本批落地并纳入合规门禁。
- 检索治理：已登记根内**未登记/撤销/未批准/过期/摘要漂移（源文档更新但未重准入）的文件一律不进索引**；`sign`（对外）受众只看 public 条目，其余 preset 看 public+internal（租户受众过滤）。
- `contracts/tools.json` 的 knowledge scan reasons 词表扩展（`unregistered/unapproved/revoked/expired/stale_hash/audience_filtered/registry_invalid`），`cli doctor` 露出治理状态（present/valid/entries，仅布尔与计数，无路径）。
- 验收反例全部落入门禁（tests/test_knowledge_registry.py）：内部条目对 sign 隐身、撤销/过期/漂移/未登记零命中、坏注册表拒绝、未知 preset 拒绝、工作区现存文档在注册表下可继续命中。

## 3. P1-3.3 Skills 准入与生命周期

- 合同：新增 `contracts/skills.json`——每个技能：路径 + sha256 + `when`（profile×preset 批准组合）+ `scripts`（可执行内容必须逐个登记 file+digest）+ `revoked`；loader 在 catalog 严格校验（fail-closed）。
- 生命周期：`scripts/verify_skills.py` 两个子命令——`sync`（按注册表合成 DSH 挂载根，缺文件或摘要漂移直接失败、无部分状态；撤销=合同变更+重同步，不再手工删目录）与 `verify`（挂载根只允许未撤销已准入条目、逐文件摘要核对、杂散文件/嵌套深度失败）。
- 接线：`scripts/start_runtime.sh` 的手工 `cp -R` 条件拷贝改为注册表驱动的 sync+verify（缺省 preset 与运行时缺省一致：company-agent→lab、minimal→boot）；`scripts/verify_dsh_profiles.py` 的技能收集与"会话技能清单期望"同样改为注册表驱动；`scripts/release_manifest.py` 的 MANAGED_FILES 纳入新脚本，发布沙箱测试通过。
- 验收反例：撤销条目不挂载且 verify 通过；杂散文件/摘要漂移/缺失准入文件均失败闭合；卸载后可按需恢复（tests/test_skills_registry.py）。
- 并行会话衔接：昨晚运维会话已把真实闭环（云弧/超算弧）写入 docs/dsh-development-manual，并把 `SLURM_JOB_ID` 记入日志；门禁的旧 `job-id` 传统词按"SLURM 环境变量身份豁免、其他 job-id 词汇仍禁"收窄语义。

## 4. P1-4 可重复验证体系（`scripts/compliance_gate.py`）

- 离线确定性门禁 13 个场景，覆盖四类：normal（能力分层、模板渲染、知识检索）、denied（未知工具×2、设备/HPC 预设拒绝、boot 调用零派发）、fault（未配置 provider 零外发、回执写入、失败闭合）、reconciliation（未确认派发→unknown→旗标、完成结局清除）。
- 报告绑定：合同 digest、技能注册表、adapter 版本、python 版本、DSH 版本钉、模型路由布尔（绝不写密钥）与模型栈证据链——输出 `docs/evidence/compliance-local.json`，版本指纹为场景清单 sha256。
- 证据链：`--model-stack-evidence` 新增绑定 `scripts/probe_model_service.py` 的产物（见 P2-5.2）；本轮实测 13/13 绿。

## 5. P2-5.1 工作台投影（`/company-workspace/agent/state`）

- `apps/company-workspace/host.mjs` 新增只读投影端点：复用同一 `company_agent.cli`（doctor + reconcile），10 秒缓存、12 秒子进程上限、256KB 输出上限，`trustedRequest` 同其他路由；投影仅限治理布尔/计数与 unknown 任务计数/请求引用——UI 不是权限源，业务状态全部来自服务端合同事实。
- `apps/company-workspace/client.js`：通用行新增"内核治理"一行（技能库/知识典准入、待对账外发条数），与既有轮询管线合并（30 秒）；`layout-model.test.mjs` 允许集合加入该只读投影。
- 跨端一致性：桌面与网页共用同一 CLI 事实源;审批与授权不在此面暴露。

## 6. P2-5.2 模型服务六点验收（`scripts/probe_model_service.py`）

- 默认离线（只产生 `executed:false` 证据）；`--live` 才触达 OpenAI 兼容端点。六个探针：tool-call 形状、SSE 流式、取消（客户端超时切流）、上下文容量登记（/models）、结构化输出、并发四路。证据只记录检查结论、上下文容量报告与 usage token 总量，不含提示词/答复正文/密钥。
- 首轮实测（公司中转 gpt-6-luna）报"流式 ✗（chunks=2 finish=0）"后建立结构化取证：逐行捕获 SSE 形状（仅键集合与 finish/usage/done 三类统计，不落正文），证实 **中转流本身规范健康**（逐 token 分片、结尾 `finish_reason: stop` + `[DONE]`，首帧负答 + 尾帧 usage 可选）。首轮结论是探针自身取证不足的伪影，不是适配层缺陷——无任何 llm 层修改需求，DSH `llm-pi-ai` 的终态映射（pi-ai `message.stopReason` → harness finish）与现状匹配。
- 探针随证据重写：`StreamingScanner` 形状扫描（含 usage 尾块、不可解析计数），流式判定 = 分片递增 + 线级 finish_reason + `[DONE]`；并发检查加"每失败通道有界重试一次"，区分瞬时传输抖动与真实服务并发上限（证据同时记录 initial/post_retry）。
- 回归：`tests/test_model_probe.py`(9) 以本地假 SSE 服务覆盖健康流/缺 finish/截断/usage 尾块/401/工具形状/结构化/并发恢复与持续失败/离线证据形态。终版实测（2026-10-23 中转 gpt-6-luna，17 tokens）**六点全绿**（`docs/evidence/model-stack-probe-2026-10-23-relay.json`）；本地 DeepSeek 端点离线时的证据如实保留。费用仍以公司平台结算为准。

## 7. 平台资产指标自动拉取（`asset.metrics`，双仓合同先行）

- **本仓合同**：providers.json uniqon 操作 + `asset.metrics`；tools.json 新工具 `quantum_asset_metrics`（input `asset_id` 句柄；输出与 asset.get 同族的 `status` + `summary[metrics]`，`scientific-metrics/1.0` 常量钉死，≤8 指标项；零新句柄）；`company.asset` 能力与 lab/algo/sign 可见列表同步；`metric-summary` 模板 sources 增补。
- **平台仓（company-quantum-platform/uniqon）**：适配器新增 `asset.metrics` 分支（只读指标表快照，无正文），CHANGELOG 记录；平台仓自己 77 项 provider 用例通过。
- **闭环**：模型链 = `quantum_asset_metrics`（平台拉表）→ `company_analysis_render`（受管模板消费快照表，结构错误 fail-closed）。上游表 schema 不符在**工具边界**即拒（不进模板不进模型）。
- **验证**：本仓本地假平台 89 项 provider 用例通过（含取表→模板链、坏 `asset_id`、错误 schema 关闭）；双仓门禁 `test_platform_compatibility.py` 修正旧测试对平台包名迁移的过时引用（company_quantum→uniqon；平台方重命名是平台仓自己的身份事实）并真实联通全链（正常取表 & 模板 audit complete & 跨租户 401 拒绝）。

## 8. 测试与文档

- 新增：`tests/test_analysis.py`(12)、`tests/test_knowledge_registry.py`(8)、`tests/test_skills_registry.py`(7)、`tests/test_compliance_report.py`(4)、`tests/test_model_probe.py`(9)。
- 同步钉死项：工具计数 27→29（test_installed_wheel、test_plugin_runtime、test_cli）、boot/sign 可见列表、快照读取 6→8、summary 家族 10→11、verify 探针 35→37、doctor 集合、start_runtime sync/verify 断言、合同清点（templates/skills）。
- UI node 套件端点不封闭问题修复（.COMPANY_AGENT_DSH_PORT 从环境泄漏到夹具），并加入只读投影白名单。
- P1/P2 状态写入 `docs/oss-survey/04-工程衔接建议.zh-CN.md` 状态行。
- 全量门禁：主仓 pytest **839 通过 / 0 失败**；UI node **24/24**；平台仓 provider 子集 **77 通过**；双仓兼容门禁真跑通过。

## 9. 对账链闭合：回执绑定业务作业引用（2026-10-23 续批）

- 合同（receipts v1.0 → **v1.1**，`contracts/results.json` + loader 字面量同步）：`fields` 新增 `business_ref`；新增 `ref_rules` 白名单——`cloud.submit → cloud_task`、`hpc.submit → slurm_number/job_name`、`device.run → twin_id`，候选字段名全部对照 tools.json 输出 schema 事实声明；`ref_max_bytes = 256`。
- 适配器：`receipts.business_ref_from_result` 只从**已过工具输出 schema 校验的成功 result** 里取首个白名单字段；`record_outcome` 仅在 `outcome + ok + completed` 且 operation 有 ref 规则时落 `business_ref`，dispatch / refused / unknown / 无规则操作 / 形状不符（含凭证形状字符类）一律拒绝并 fail-closed（outcome 丢弃、dispatch 直接拒发）。provider 诊断通道字段集不变：共享事件不携带 ref，伪造事件字段被忽略，唯一来源是显式提取参数。
- 读侧：`reconcile` 的 `unknown` / `recent` 行与 CLI、工作台只读投影自动透传 `business_ref`——操作员拿 `request_id ↔ 平台侧作业号` 对照平台事实；旧版（v1.0）回执看列集不匹配按坏行跳过，诚实降级不做兼容伪造。
- 合规门禁：`resolved-clears` 场景升级为「清除旗标并绑定业务引用」；`docs/evidence/compliance-local.json` 已随新合同 digest 重生成（13/13 绿）。
- 测试：`tests/test_receipts.py` 新增 4 组门禁（提取规则跟随合同、仅 ok-outcome 可绑定、伪造事件字段不生效、e2e 平台引用链），拒绝/丢包路径补 ref 空值断言。
- 全量门禁（续批后）：主仓 pytest **843 通过 / 0 失败**；UI node **24/24**；平台兼容门禁真跑通过；`docs/evidence/compliance-local.json` 13/13 绿。

## 10. 遗留（下一批)

- 比特级/大数据学界产物仍走平台资产语义；`quantum_asset_metrics` 已补"平台取数"位，其余类型（如 HPC 结果文件的指标化）走各自能力（HPC 通道已有 file 拉取工具）。
- 本地 DeepSeek 端点离线时的六点验收留待其在线后补测（证据形态已就绪）。
