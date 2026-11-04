# UnitQC Company Agent

本仓是幺正量子的公司级 Agent 工程，直接运行在 DeepSeek Harness（DSH）上。它不是新的 Agent Loop，也不实现科学算法。

## 定位

- DSH 负责模型、会话、工具生命周期、事件、Profile、Skill 和子代理。
- `company-quantum-platform` 负责公司量子算法、资产和科学结果；算法名单以平台 `component_id` 目录为准，Q-agent 只对接目录与运行接口。
- 模拟器、编译器和设备执行通过独立 provider bridge 接入。
- 量子能力作为 `company-agent-quantum` capability pack 维护。
- 公司知识库、未来业务能力和其他 capability pack 共用同一 Agent Runtime。

自动科研与实验契约在 [`research-layer/`](research-layer/README.md)。它与本仓的 Agent 运行时分开开发，放在同一仓库里，避免互相覆盖 `contracts/`、`docs/` 和 `packages/`。

## 不变量

- 对外科学句柄只有 `asset_id`、`circuit_id`、`twin_id`。
- 只有 ionstack TwinRun 对应的设备 provider 可签发 `twin_id`。
- 模拟器和编译器不得返回 `twin_id`，不得声称 `qccd-twin` 来源。
- 设备执行必须经过确定性策略和人工批准。
- CAL、shuttle、密钥和大体量科学正文不进入工具结果。
- 公司科学包不被 Agent 直接 import；通过严格 provider bridge 调用。

## 快速检查

```bash
python3 -m venv /tmp/company-agent-dev
source /tmp/company-agent-dev/bin/activate
python -m pip install --require-hashes -r runtime/python-dev.lock
bash scripts/bootstrap_dsh.sh
python scripts/verify_acceptance.py
PYTHONPATH=src python3 -m company_agent.cli capabilities
PYTHONPATH=src python3 -m company_agent.cli doctor
```

## DSH

```bash
bash scripts/bootstrap_dsh.sh
python3 scripts/verify_dsh_profiles.py
bash scripts/start_runtime.sh
```

`bootstrap_dsh.sh` 会按 `runtime/pnpm-lock.yaml` 冻结安装顶层 DSH CLI `0.1.5-rc.2`、Node `22.22.0` 和 pnpm `12.5.1`；DSH 的传递组件版本由对应锁文件分别确定，不假定全部组件与 CLI 同版。系统自带 Node 20 不再直接承载 DSH；`start_runtime.sh` 始终使用这份隔离运行时。DSH 的可写状态默认放在 `${XDG_CACHE_HOME:-$HOME/.cache}/unitqc-company-agent/dsh-home`，避免 WSL 的 `/mnt/*` 文件系统无法落实凭据文件的仅属主权限；需要固定位置时可设置 `COMPANY_AGENT_DSH_HOME`。验证脚本为完整 profile 的 `boot/lab/algo/sign` 和最小 profile 的 `boot/algo` 六个合法组合分别分配独立临时 `DSH_HOME`，先检查展开配置，再启动 Web Runtime、通过认证接口真实创建会话，并核对合同推导的工具清单及与启动脚本一致的 Skill 集合；还验证仅有 system-trust 的 `company-agent` preset、复制被只读策略拒绝、切换到非受管 preset 被拒绝且会话工具不变。最小 profile 的 `lab/sign` 必须启动失败。失败会区分为 `config_error`、`plugin_error`、`credential_error` 或一般 `startup_error`。

默认 profile 是 `company-agent`。造包使用 `company-agent-minimal`，该 profile 不加载设备插件。两个 profile 都关闭 DSH 内置 preset 和用户可写 preset 根，只从项目复制到隔离运行目录的 system-trust preset 根挂载 `company-agent` 组合，避免创建或切换到带 shell 的编码 preset 绕过设备审批。完整 profile 只在宿主侧注册官方 Codex provider，并保持 `permissionMode: never`、`inheritsParentContext: false`；它不挂载模型可见的 Codex 委派工具，因此不会继承 Company Agent 的设备工具。

## 通过界面使用

1. 运行 `bash scripts/start_runtime.sh`，在本机浏览器打开终端输出的带登录 token 的完整地址。默认监听 `127.0.0.1:3081`；该地址中的 token 是访问凭据，不要分享或提交到仓库。
2. 首次出现 `Add an API key to get started` 时，在界面配置真实的 DeepSeek API key；也可以在启动进程前设置 `DEEPSEEK_API_KEY`。`Configure later` 只会关闭提示，不表示模型已可调用。
3. 点击 `Choose workspace` 选择实际工作目录，保持 `Company Agent`，创建会话。例如先发送“请列出公司能力，并检索设备执行的审批要求”。模型可调用 `company_capabilities` 和 `company_knowledge_search`，工具记录可展开查看。
4. 科学任务先用 `quantum_algorithm_catalog` 向平台发现当前算法，再用 `company_workflow_validate` 校验计划，然后调用算法、资产、电路导出、模拟或编译工具。按任务需要配置下文的真实服务地址和 token；修改环境变量后须重启 Runtime，现有进程不会自动继承新值。新算法的目录、机器参数合同及可信执行入口在 `company-quantum-platform` 统一注册并通过服务准入后，不必改 Agent 分支；仅登记元数据或配置 URL/token 不会使其自动可运行。
5. 设备执行出现 `Waiting for approval` 后，核对 `quantum_device_run` 的电路句柄和执行参数。`Reject` 拒绝本次调用；`Allow once` 只批准本次调用，再次执行仍需批准。

本地知识检索和工作流校验不依赖科学服务，但通过聊天界面自动选择工具仍需要可用的模型。`company-agent-minimal` 默认只暴露本地公司工具，不加载设备插件。

`verify_dsh_profiles.py` 通过表示配置、会话及工具/Skill 清单正确，**不表示真实模型和科学服务已验收**。`doctor` 只检查环境配置，不发起服务调用，也不读取 DSH 界面保存的模型凭据。最终业务验收须使用真实模型、实际资产/电路及对应服务，并在设备执行前人工批准。

## Provider 配置

Agent 使用严格的 `company-agent-provider/1.0` JSON 信封。每类真实服务必须同时配置地址及对应凭据：

- 平台：`COMPANY_QUANTUM_PLATFORM_INVOKE_URL` 和 `COMPANY_QUANTUM_PLATFORM_TOKEN`。
- 模拟器：`COMPANY_AGENT_SIMULATOR_INVOKE_URL` 和 `COMPANY_AGENT_SIMULATOR_TOKEN`。
- 编译器：`COMPANY_AGENT_COMPILER_INVOKE_URL` 和 `COMPANY_AGENT_COMPILER_TOKEN`。
- 设备：`COMPANY_AGENT_DEVICE_INVOKE_URL` 和 `COMPANY_AGENT_DEVICE_TOKEN`。

- `company-agent doctor` 同时报告四个科学 provider 与 `DEEPSEEK_API_KEY` 是否已配置，只报告布尔状态和所需 URL/token 环境变量名，不回显值。
- URL 或合同声明的 token 未配置时，调用必须诚实失败，不会生成本地科学结果或伪造结果。
- 额外知识目录只有同时设置 `COMPANY_AGENT_KNOWLEDGE_PATH` 和 `COMPANY_AGENT_ENABLE_CONFIGURED_KNOWLEDGE=1` 才会进入检索；生产默认只读项目管理的内置知识根。检索返回的 `version` 为内容 SHA-256 摘要；每次检索限制目录条目数、累计读取字节数及最多 8 条命中。
- `contracts/results.json` 统一规定结果总预算（紧凑 UTF-8 JSON 最多 64,000 字节）及 provider 输出限制。禁止内容和超限结果整体失败，不会静默截断科学结果；服务端错误正文不进入模型上下文。
- 生产启动固定使用项目 `contracts/`，忽略外部 `COMPANY_AGENT_CONTRACTS_DIR`；直接使用 CLI 时仍可显式指定合同目录进行测试。Python bridge 使用 `-P`，避免从启动工作目录导入同名伪造模块。
- 验证脚本清除真实模型和科学 provider 的地址/凭据，禁用本地 HTTP 验证的环境代理。它只验证运行组合，不能代替真实业务验收。

## 统一验收与合同迁移

- `python scripts/verify_acceptance.py` 默认只做本地/回环验收，包含单仓全量测试、真实 DSH 固定模型审批生命周期、六组合会话装配、静态检查和中文检索基准；报告分别记录 passed/failed/skipped/deselected，明确不包含独立双仓门禁。验收入口清除继承的 pytest 选项与外部插件配置，使用本次结构化执行证据核对完整收集、筛选和执行；零测试或异常筛除不能作为通过。先运行 `bash scripts/bootstrap_dsh.sh` 安装锁定 Runtime。
- `python scripts/benchmark_company_agent.py --repeats 10` 输出检索召回、排名、逐次耗时样本、中位数和 nearest-rank 第 95 百分位；冷 Node→Python CLI→回环服务计时不包含模型或完整 DSH 会话。固定样例不是实际业务语料或模型效果验收。
- 独立双仓门禁：`COMPANY_AGENT_PLATFORM_SOURCE=/absolute/company-quantum-platform python -m pytest -q -m platform_compatibility tests/test_platform_compatibility.py`。实际平台 adapter 在隔离进程启动回环 HTTP，执行器只使用无科学行为替身。默认 Agent 测试明确不选择此需额外源码的门禁；单仓通过不代表双仓已验收。指定门禁却缺少源码时失败，不跳过。
- 已脱敏外部语料可用 `scripts/evaluate_knowledge.py` 评测；输入格式和限制见 [知识评测说明](docs/knowledge-evaluation.zh-CN.md)。
- 工具和结果合同现为 `2.0.0`：算法运行必须同时提供目录响应的 `catalog_version` 和条目的 `component_version=version`，不隐式选择 latest。新增外部工作流 `inputs`、类型化科学指标、当前 preset 可见性与参考资料信任标记。`valid` 只表示静态结构和参数有效，不证明执行许可。迁移详见 [2.0 迁移说明](docs/contracts-2.0-migration.zh-CN.md)。
- 设备发送后超时、断连或取消可能报告结果未知；没有自动重试，`request_id` 仅为关联 ID，不保证幂等。需要运维核对服务状态后才能决定新调用。
- `python scripts/verify_acceptance.py --mode real --asset-id asset_example --circuit-id circ_example --algorithm example` 只输出配置预检和人工监督验收用例；显式增加 `--launch` 才打开隔离的既有 DSH 界面。替换为获准的真实测试资产，设备仍须逐次人工审批。配置存在不等于服务通过，业务检查保留 `blocked`，不从界面退出推断成功。
- `python scripts/record_closure.py --platform-source /absolute/company-quantum-platform --platform-python /absolute/quality-python --output /absolute/new-evidence-directory` 连续执行本地、平台边界/质量、双仓兼容和基准五组门禁；输出目录须不存在，报告绑定两仓源码/测试首尾摘要并保留失败，不重试掩盖失败。使用已安装依赖，只做合成/回环验证，不构建平台发行候选。
- 受管生产发布和人工证据格式见 [部署与证据说明](docs/deployment-and-evidence.zh-CN.md)。生产清单包含 Runtime 和两个 profile 的完整依赖树；签认与信任文件必须位于发布和 Runtime 根之外。校验先验证同一份清单的外部签认，再核对内容和运行版本探测；无效签认不得执行待验 Node。工作区开发启动不代表生产部署。
- 开发依赖更新：先安装现有哈希锁，再执行 `bash scripts/lock_python.sh --upgrade`；wheel 在临时源码副本使用同一锁构建，不污染工作区。

当前字段、正反例与边界见 [2.0 迁移说明](docs/contracts-2.0-migration.zh-CN.md)；[1.2 迁移记录](docs/contracts-1.2-migration.zh-CN.md) 与 [2026-09-29 性能记录](docs/performance-2026-09-29.zh-CN.md) 作为历史证据保留，不替代当前验收。

## 产品界面设计

当前方案以 [v0.7 DSH 插件 / MCP / Skills 集成设计](docs/company-agent-dsh-integration-v0.7.zh-CN.md) 为准：在 DeepSeek Harness 上使用公司本地模型，装配受管通用插件、MCP（工具与资源连接协议）及常用 Skills。知识库、云平台、HPC 和量子算法是并列服务，量子能力只是其中一类；日常使用与通用 Agent 一样。

[v0.6 能力与验收](docs/company-agent-general-capabilities-v0.6.zh-CN.md) 保留实际文件、办公、编程、分析和调研交付要求，但这些是能力清单，不是全部自研清单。优先复用固定版本 DSH 与成熟扩展，只补公司合同适配、隔离、身份、鲁棒性和产品接入；不重建 Agent 循环或每类能力的后端。插件安装 / MCP 发现 / Skill 配置不等于已授权或验收，当前生产白名单也未自动开放这些通用工具。

通用命令按合同在隔离边界内执行，不开放生产宿主 shell 或可切换的 shell 编码 preset；Codex 宿主隔离与设备逐次审批保持不变。[v0.4 公司级设计](docs/company-agent-platform-plan-v0.4.zh-CN.md) 的知识与身份边界继续沿用。

三栏视觉延续 [v0.5 界面基准](docs/workspace-ui-baseline-v0.5.zh-CN.md)，最新展示使用 DSH 的 Slot 组合：真实工作空间 / 会话列表和原生设置并入左栏，中间显示公司内容，右侧直接渲染未经修改的原生对话组件。右栏不再嵌套整套 DSH 网页；各栏可收起、恢复和拖动调宽，草稿不随隐藏丢失。

启动方式见 [原生 DSH 三栏展示](docs/native-dsh-demo.zh-CN.md)：运行 `python3 scripts/serve_workspace_demo.py`，打开程序打印的本机启动链接。它使用隔离展示状态、最小受管 profile 和 `boot`，不继承模型 / 科学服务凭据。公司账号、云 / HPC 和示例文件仍未接入业务；真实会话列表、新会话、模型设置已经使用 DSH 原生组件。

原型交互回归独立运行：`npm ci --prefix tests/ui`，然后 `npm test --prefix tests/ui`；不安装到受管 DSH Runtime，也不调用模型或科学服务。

## 审查与实施记录

2026-10-26 建立 LaTeX 工具链阶段 0 黄金矩阵与兼容性门禁：固定清单的黄金项目集、直驱引擎的矩阵脚本、诚实未配置语义与 opt-in `latex_toolchain` 门禁接线，见 [LaTeX 工具链阶段 0](docs/latex-lab-phase0.zh-CN.md)。2026-10-09 续行修复发布校验顺序与离线验收完整性，当前复验结果、环境恢复和独立证据见 [续行实施记录](docs/implementation-2026-10-09.zh-CN.md)。2026-10-08 四阶段改造、收尾门禁、失败尝试和证据范围见 [历史实施记录](docs/implementation-2026-10-08.zh-CN.md)。记录器核对枚举输入的首尾内容、文件集合及权限；它没有冻结整个主机或证明运行中未发生瞬时改动。已安装依赖不在该源码清单内，完整生产依赖核验另由发布清单负责。

2026-09-28 原始审查及 2026-09-29 全量整改交付见 [工程审查记录](docs/review-2026-09-28.zh-CN.md)。本地通过与真实模型、服务、设备上线验收明确分开。
