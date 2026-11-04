import {
  Callout,
  Card,
  CardBody,
  CardHeader,
  Divider,
  Grid,
  H1,
  H2,
  H3,
  Link,
  Pill,
  Row,
  Select,
  Stack,
  Stat,
  Table,
  Text,
  useCanvasState,
  useHostTheme,
  useMemo,
} from "cursor/canvas";

const projects = [
  { category: "编程代理与方法", name: "obra/superpowers", url: "https://github.com/obra/superpowers", role: "把需求澄清、计划、TDD、分支、评审和收尾固化为可触发技能。", signal: "MIT；活跃；方法论成熟", decision: "采用方法层" },
  { category: "编程代理与方法", name: "karpathy/autoresearch", url: "https://github.com/karpathy/autoresearch", role: "固定时间预算、固定指标、单一可修改面、保留或丢弃实验。", signal: "研究原型；README 明确约束", decision: "采用实验契约" },
  { category: "编程代理与方法", name: "snarktank/ralph", url: "https://github.com/snarktank/ralph", role: "每轮启动新代理上下文，用 PRD、进度文件和 Git 历史跨轮次记忆。", signal: "社区实现；需自审脚本", decision: "实验语义参考" },
  { category: "编程代理与方法", name: "badlogic/pi-mono", url: "https://github.com/badlogic/pi-mono", role: "极简可扩展代理运行时，支持技能、扩展、RPC、JSON/打印模式和 TypeScript SDK。", signal: "MIT；活跃；可嵌入", decision: "设计参照" },
  { category: "编程代理与方法", name: "OpenHands/OpenHands", url: "https://github.com/OpenHands/OpenHands", role: "自托管代理控制中心，可连接本地、Docker、虚拟机、云和定时自动化。", signal: "MIT；活跃；有 Agent Canvas", decision: "参照，不部署" },
  { category: "编程代理与方法", name: "OpenHands/software-agent-sdk", url: "https://github.com/OpenHands/software-agent-sdk", role: "Python/TypeScript/REST 代理 SDK，支持临时 Docker/Kubernetes 工作区。", signal: "活跃；SDK/Server 分层清晰", decision: "参照，不部署" },
  { category: "编程代理与方法", name: "SWE-agent/SWE-agent", url: "https://github.com/SWE-agent/SWE-agent", role: "从 GitHub issue 到代码修复、测试和补丁的自动软件工程基线。", signal: "MIT；NeurIPS 2024；活跃", decision: "参照，不部署" },
  { category: "编程代理与方法", name: "Aider-AI/aider", url: "https://github.com/Aider-AI/aider", role: "终端内结对编程、代码编辑、测试和 Git 工作流。", signal: "Apache-2.0；成熟社区", decision: "参照，不部署" },
  { category: "编程代理与方法", name: "Cline/Cline", url: "https://github.com/Cline/Cline", role: "IDE/CLI/SDK 代理，适合作为交互式开发入口和人工接管入口。", signal: "Apache-2.0；活跃", decision: "参照，不部署" },
  { category: "编程代理与方法", name: "continuedev/continue", url: "https://github.com/continuedev/continue", role: "开源编码代理和开发者工具，适合接入团队模型与上下文。", signal: "Apache-2.0；活跃", decision: "参照，不部署" },
  { category: "编程代理与方法", name: "google-gemini/gemini-cli", url: "https://github.com/google-gemini/gemini-cli", role: "终端代理和工具调用入口，适合作为多模型执行器之一。", signal: "Apache-2.0；活跃", decision: "参照，不部署" },
  { category: "编程代理与方法", name: "openai/codex", url: "https://github.com/openai/codex", role: "轻量终端编码代理，适合隔离工作区中的代码任务。", signal: "Apache-2.0；活跃", decision: "参照，不部署" },
  { category: "编程代理与方法", name: "block/goose", url: "https://github.com/block/goose", role: "可扩展代理，覆盖安装、执行、编辑、测试和模型接入。", signal: "Apache-2.0；活跃", decision: "参照，不部署" },
  { category: "编程代理与方法", name: "qodo-ai/pr-agent", url: "https://github.com/qodo-ai/pr-agent", role: "自动 PR 描述、审查、改进建议和代码质量反馈。", signal: "MIT；活跃", decision: "采用 PR 评审" },
  { category: "编程代理与方法", name: "github/spec-kit", url: "https://github.com/github/spec-kit", role: "规范驱动开发工具，先生成规格再分解实现。", signal: "MIT；活跃；大社区", decision: "采用需求入口" },
  { category: "编程代理与方法", name: "langchain-ai/langgraph", url: "https://github.com/langchain-ai/langgraph", role: "有状态、可恢复、可人工介入的代理图编排。", signal: "活跃；图状态模型", decision: "参照，不部署" },

  { category: "文献与自动科研", name: "SakanaAI/AI-Scientist", url: "https://github.com/SakanaAI/AI-Scientist", role: "从研究想法、代码、实验、分析到论文草稿的自动科研原型。", signal: "研究原型；运行 LLM 代码有风险", decision: "沙箱参考" },
  { category: "文献与自动科研", name: "stanford-oval/storm", url: "https://github.com/stanford-oval/storm", role: "多轮检索、知识整理和带引用长报告生成。", signal: "MIT；研究系统；活跃", decision: "采用检索流程" },
  { category: "文献与自动科研", name: "Future-House/paper-qa", url: "https://github.com/Future-House/paper-qa", role: "针对科学文献的高准确率问答和引用支持。", signal: "Apache-2.0；科学文档方向", decision: "采用文献问答" },
  { category: "文献与自动科研", name: "langchain-ai/open_deep_research", url: "https://github.com/langchain-ai/open_deep_research", role: "可配置深度研究代理，支持多模型、搜索工具、MCP 和评测。", signal: "MIT；快照显示 archived；参考为主", decision: "参考评测" },
  { category: "文献与自动科研", name: "microsoft/markitdown", url: "https://github.com/microsoft/markitdown", role: "把 PDF、Office、网页等资料转换为模型可处理的 Markdown。", signal: "MIT；活跃；大社区", decision: "采用入口转换" },
  { category: "文献与自动科研", name: "VikParuchuri/marker", url: "https://github.com/VikParuchuri/marker", role: "高质量 PDF 到 Markdown/JSON，适合科学论文结构化。", signal: "Apache-2.0；活跃", decision: "采用 PDF 解析" },
  { category: "文献与自动科研", name: "opendatalab/MinerU", url: "https://github.com/opendatalab/MinerU", role: "复杂文档解析为 LLM-ready Markdown/JSON，适合批量文献管线。", signal: "活跃；许可证需逐版本核查", decision: "候选解析器" },
  { category: "文献与自动科研", name: "grobid/grobid", url: "https://github.com/kermitt2/grobid", role: "从学术 PDF 提取标题、作者、章节、引用和文献元数据。", signal: "Apache-2.0；长期维护", decision: "采用元数据抽取" },
  { category: "文献与自动科研", name: "allenai/s2orc-doc2json", url: "https://github.com/allenai/s2orc-doc2json", role: "PDF、TeX、JATS 到论文 JSON 的解析器。", signal: "Apache-2.0；专项工具", decision: "补充解析" },
  { category: "文献与自动科研", name: "zotero/zotero", url: "https://github.com/zotero/zotero", role: "文献库、附件、标签和人工审阅的长期资产层。", signal: "成熟产品；许可证和插件边界需审查", decision: "文献资产入口" },
  { category: "文献与自动科研", name: "citation-js/citation-js", url: "https://github.com/citation-js/citation-js", role: "跨格式引用解析、转换和 BibTeX/CSL 数据处理。", signal: "MIT；工具成熟", decision: "采用引用处理" },
  { category: "文献与自动科研", name: "jgm/pandoc", url: "https://github.com/jgm/pandoc", role: "Markdown、LaTeX、DOCX、HTML 等学术交付格式互转。", signal: "GPL；成熟；发布前需许可证评估", decision: "交付转换器" },

  { category: "实验、评测与追踪", name: "openai/evals", url: "https://github.com/openai/evals", role: "LLM 和工具系统的可重复评测框架与评测注册表。", signal: "活跃；自定义 eval 需审查政策", decision: "采用 Agent 评测" },
  { category: "实验、评测与追踪", name: "EleutherAI/lm-evaluation-harness", url: "https://github.com/EleutherAI/lm-evaluation-harness", role: "统一语言模型基准、few-shot 评测和结果比较。", signal: "MIT；活跃；社区广", decision: "模型基准" },
  { category: "实验、评测与追踪", name: "mlflow/mlflow", url: "https://github.com/mlflow/mlflow", role: "实验跟踪、模型注册、Agent tracing、评测、成本和访问控制。", signal: "Apache-2.0；生产生态成熟", decision: "首选追踪层" },
  { category: "实验、评测与追踪", name: "wandb/wandb", url: "https://github.com/wandb/wandb", role: "训练和实验追踪、可视化、模型管理与团队协作。", signal: "MIT；成熟；云服务耦合需评估", decision: "可选追踪层" },
  { category: "实验、评测与追踪", name: "clearml/clearml", url: "https://github.com/clearml/clearml", role: "实验、数据、流水线、编排、调度和服务一体化。", signal: "Apache-2.0；平台化较完整", decision: "可选一体化" },
  { category: "实验、评测与追踪", name: "aimhubio/aim", url: "https://github.com/aimhubio/aim", role: "轻量开源实验追踪和指标可视化。", signal: "Apache-2.0；活跃", decision: "轻量备选" },
  { category: "实验、评测与追踪", name: "iterative/dvc", url: "https://github.com/iterative/dvc", role: "数据/模型版本、可复现流水线、Git 关联实验和远端对象存储。", signal: "Apache-2.0；成熟", decision: "采用数据版本" },
  { category: "实验、评测与追踪", name: "pachyderm/pachyderm", url: "https://github.com/pachyderm/pachyderm", role: "数据中心流水线和数据版本化，适合批处理数据血缘。", signal: "Apache-2.0；Kubernetes 生态", decision: "大数据备选" },
  { category: "实验、评测与追踪", name: "Netflix/metaflow", url: "https://github.com/Netflix/metaflow", role: "Python 优先的 AI/ML 系统开发、运行、部署和恢复。", signal: "Apache-2.0；生产背景", decision: "Python 工作流备选" },
  { category: "实验、评测与追踪", name: "determined-ai/determined", url: "https://github.com/determined-ai/determined", role: "分布式训练、超参搜索、实验跟踪和资源管理。", signal: "Apache-2.0；平台项目", decision: "训练集群备选" },
  { category: "实验、评测与追踪", name: "kubeflow/katib", url: "https://github.com/kubeflow/katib", role: "Kubernetes 上的自动机器学习和超参数优化。", signal: "Apache-2.0；Kubernetes 原生", decision: "K8s 搜索备选" },
  { category: "实验、评测与追踪", name: "optuna/optuna", url: "https://github.com/optuna/optuna", role: "定义即运行的搜索空间、剪枝、并行试验和可视化。", signal: "MIT；成熟；活跃", decision: "采用黑盒优化" },
  { category: "实验、评测与追踪", name: "facebook/Ax", url: "https://github.com/facebook/Ax", role: "贝叶斯优化、多目标和自适应实验设计。", signal: "MIT；研究/工程并用", decision: "采用主动实验" },
  { category: "实验、评测与追踪", name: "google-deepmind/optax", url: "https://github.com/google-deepmind/optax", role: "JAX 优化器和梯度处理组件，适合算法搜索底层。", signal: "Apache-2.0；DeepMind 维护", decision: "算法组件" },

  { category: "编排、超算与资源", name: "temporalio/temporal", url: "https://github.com/temporalio/temporal", role: "持久执行、定时器、重试、信号和外部异步任务恢复。", signal: "MIT；成熟；适合长流程", decision: "首选总控" },
  { category: "编排、超算与资源", name: "PrefectHQ/prefect", url: "https://github.com/PrefectHQ/prefect", role: "Python 工作流、重试、缓存、事件自动化和调度 UI。", signal: "Apache-2.0；活跃", decision: "MVP 备选" },
  { category: "编排、超算与资源", name: "apache/airflow", url: "https://github.com/apache/airflow", role: "定时和依赖型批处理，适合报表、数据刷新和固定 DAG。", signal: "Apache-2.0；生态成熟", decision: "固定 DAG" },
  { category: "编排、超算与资源", name: "dagster-io/dagster", url: "https://github.com/dagster-io/dagster", role: "数据资产、开发、生产和观测一体化。", signal: "Apache-2.0；活跃", decision: "数据资产备选" },
  { category: "编排、超算与资源", name: "flyteorg/flyte", url: "https://github.com/flyteorg/flyte", role: "类型安全的 Kubernetes 分布式编排、ML pipeline 和 Agent。", signal: "Apache-2.0；活跃", decision: "强类型编排备选" },
  { category: "编排、超算与资源", name: "argoproj/argo-workflows", url: "https://github.com/argoproj/argo-workflows", role: "Kubernetes 原生容器工作流和批量任务。", signal: "Apache-2.0；成熟", decision: "K8s 批处理" },
  { category: "编排、超算与资源", name: "kubernetes-sigs/kueue", url: "https://github.com/kubernetes-sigs/kueue", role: "队列、配额、fair sharing、gang scheduling、MultiKueue 和 admission checks。", signal: "Apache-2.0；CNCF 生态；生产使用", decision: "K8s 配额层" },
  { category: "编排、超算与资源", name: "volcano-sh/volcano", url: "https://github.com/volcano-sh/volcano", role: "Kubernetes 批处理、队列、gang 和高性能工作负载调度。", signal: "Apache-2.0；CNCF 项目", decision: "K8s 调度备选" },
  { category: "编排、超算与资源", name: "flux-framework/flux-core", url: "https://github.com/flux-framework/flux-core", role: "HPC 内部资源管理和作业内调度。", signal: "LGPL-3.0；HPC 专项", decision: "Slurm 备选" },
  { category: "编排、超算与资源", name: "SchedMD/slurm", url: "https://github.com/SchedMD/slurm", role: "CPU/GPU/HPC 集群的队列、配额、节点和作业生命周期。", signal: "HPC 行业基线；部署许可需核查", decision: "超算主调度" },
  { category: "编排、超算与资源", name: "skypilot-org/skypilot", url: "https://github.com/skypilot-org/skypilot", role: "跨 Kubernetes、Slurm、云和多 GPU 供应商的资源抽象、故障切换和自动回收。", signal: "Apache-2.0；活跃；多云", decision: "采用云资源层" },
  { category: "编排、超算与资源", name: "Parsl/Parsl", url: "https://github.com/Parsl/Parsl", role: "Python 并行脚本和跨 HPC/云资源执行。", signal: "活跃；HPC 工作流生态", decision: "HPC Python 备选" },
  { category: "编排、超算与资源", name: "nextflow-io/nextflow", url: "https://github.com/nextflow-io/nextflow", role: "可移植、可恢复的数据/计算 pipeline，适合批量科研流程。", signal: "Apache-2.0；成熟", decision: "批量科研备选" },
  { category: "编排、超算与资源", name: "snakemake/snakemake", url: "https://github.com/snakemake/snakemake", role: "以文件依赖和规则描述可复现科研流水线。", signal: "活跃；科研用户广", decision: "复现 pipeline" },
  { category: "编排、超算与资源", name: "ray-project/ray", url: "https://github.com/ray-project/ray", role: "分布式 Python、Actor、训练、调参和 Agent 执行。", signal: "Apache-2.0；生态成熟", decision: "并行执行层" },
  { category: "编排、超算与资源", name: "ray-project/kuberay", url: "https://github.com/ray-project/kuberay", role: "在 Kubernetes 上部署和调度 Ray 集群、作业和服务。", signal: "Apache-2.0；K8s 生态", decision: "Ray 集群适配" },

  { category: "测试、安全与可观测", name: "microsoft/playwright", url: "https://github.com/microsoft/playwright", role: "跨 Chromium、Firefox、WebKit 的端到端、浏览器代理和 trace 测试。", signal: "Apache-2.0；成熟；活跃", decision: "前端首选" },
  { category: "测试、安全与可观测", name: "cypress-io/cypress", url: "https://github.com/cypress-io/cypress", role: "前端组件和端到端测试，适合快速反馈。", signal: "MIT；成熟", decision: "前端备选" },
  { category: "测试、安全与可观测", name: "SeleniumHQ/selenium", url: "https://github.com/SeleniumHQ/selenium", role: "跨浏览器 WebDriver 自动化和历史兼容性测试。", signal: "Apache-2.0；长期成熟", decision: "兼容性补充" },
  { category: "测试、安全与可观测", name: "pytest-dev/pytest", url: "https://github.com/pytest-dev/pytest", role: "Python 单元、集成和回归测试的基础执行器。", signal: "MIT；成熟", decision: "后端首选" },
  { category: "测试、安全与可观测", name: "HypothesisWorks/hypothesis", url: "https://github.com/HypothesisWorks/hypothesis", role: "性质测试、自动生成边界输入和缩减失败样例。", signal: "活跃；Python 测试基线", decision: "采用性质测试" },
  { category: "测试、安全与可观测", name: "testcontainers/testcontainers-python", url: "https://github.com/testcontainers/testcontainers-python", role: "在测试中启动数据库、消息队列和依赖服务。", signal: "Apache-2.0；活跃", decision: "集成测试" },
  { category: "测试、安全与可观测", name: "semgrep/semgrep", url: "https://github.com/semgrep/semgrep", role: "代码模式、安全规则和快速静态分析。", signal: "开源引擎；规则/许可需核查", decision: "静态扫描" },
  { category: "测试、安全与可观测", name: "github/codeql", url: "https://github.com/github/codeql", role: "语义代码安全分析和数据流漏洞检测。", signal: "GitHub 维护；运行政策需核查", decision: "安全门" },
  { category: "测试、安全与可观测", name: "aquasecurity/trivy", url: "https://github.com/aquasecurity/trivy", role: "镜像、文件系统、依赖和配置漏洞扫描。", signal: "Apache-2.0；活跃", decision: "镜像安全" },
  { category: "测试、安全与可观测", name: "anchore/syft", url: "https://github.com/anchore/syft", role: "生成软件物料清单，记录代理和实验容器的供应链。", signal: "Apache-2.0；活跃", decision: "SBOM" },
  { category: "测试、安全与可观测", name: "open-telemetry/opentelemetry-collector", url: "https://github.com/open-telemetry/opentelemetry-collector", role: "统一采集 Agent、工作流、HPC、实验和前端的 traces/metrics/logs。", signal: "Apache-2.0；CNCF 生态", decision: "观测总线" },
  { category: "测试、安全与可观测", name: "getsentry/sentry", url: "https://github.com/getsentry/sentry", role: "异常聚合、发布回归、性能和用户侧错误追踪。", signal: "活跃；生产生态成熟", decision: "异常监控" },

  { category: "量子与算法执行示例", name: "Qiskit/qiskit", url: "https://github.com/Qiskit/qiskit", role: "量子电路、算子、Sampler/Estimator、transpiler 和后端抽象。", signal: "Apache-2.0；大型生态", decision: "通用量子基线" },
  { category: "量子与算法执行示例", name: "PennyLaneAI/pennylane", url: "https://github.com/PennyLaneAI/pennylane", role: "可微量子编程、量子机器学习和多后端接口。", signal: "Apache-2.0；活跃", decision: "可微算法" },
  { category: "量子与算法执行示例", name: "NVIDIA/cuda-quantum", url: "https://github.com/NVIDIA/cuda-quantum", role: "量子—经典混合编程、GPU 模拟和多后端执行。", signal: "Apache-2.0；活跃；硬件生态耦合", decision: "GPU/量子混合" },
  { category: "量子与算法执行示例", name: "unitaryfoundation/mitiq", url: "https://github.com/unitaryfoundation/mitiq", role: "零噪声外推、PEC、读出缓解、QSE 等误差缓解。", signal: "GPL-3.0；科研工具成熟", decision: "误差缓解" },
  { category: "量子与算法执行示例", name: "quantumlib/Stim", url: "https://github.com/quantumlib/Stim", role: "高速稳定子电路模拟和量子纠错实验。", signal: "高性能专项工具；许可证需审查", decision: "QEC 模拟" },
  { category: "量子与算法执行示例", name: "quantumlib/PyMatching", url: "https://github.com/quantumlib/PyMatching", role: "匹配解码器和量子纠错 syndrome 后处理。", signal: "活跃；QEC 专项", decision: "解码基线" },
  { category: "量子与算法执行示例", name: "quantumlib/OpenFermion", url: "https://github.com/quantumlib/OpenFermion", role: "费米子系统、量子化学哈密顿量和量子算法表示。", signal: "Apache-2.0；研究生态", decision: "量子化学表示" },
  { category: "量子与算法执行示例", name: "Pasqal-io/Pulser", url: "https://github.com/pasqal-io/Pulser", role: "中性原子设备的脉冲级序列、模拟和硬件约束。", signal: "Apache-2.0；硬件专用", decision: "脉冲/设备参考" },
] as const;

const categoryOptions = [
  { value: "全部", label: "全部项目" },
  { value: "编程代理与方法", label: "编程代理与方法" },
  { value: "文献与自动科研", label: "文献与自动科研" },
  { value: "实验、评测与追踪", label: "实验、评测与追踪" },
  { value: "编排、超算与资源", label: "编排、超算与资源" },
  { value: "测试、安全与可观测", label: "测试、安全与可观测" },
  { value: "量子与算法执行示例", label: "量子与算法执行示例" },
];

const dshStack = [
  { name: "deepseek-ai/deepseek-harness", url: "https://github.com/deepseek-ai/deepseek-harness", kind: "官方 Harness", role: "公司统一 Agent 运行框架；一切皆插件，含 Web/桌面/headless/SDK 形态。", note: "public preview，需锁版本" },
  { name: "deepseek-ai/dsh-superagent-prototype", url: "https://github.com/deepseek-ai/dsh-superagent-prototype", kind: "编码协作插件", role: "计划按完整 Super-agent 开源接入：Router/Worker、工单、订阅直通、存算分离与 Watchdog。", note: "2026-10-31 原型已开源；五模块按计划假设，本工程不重写" },
  { name: "cordiverse/cordis", url: "https://github.com/cordiverse/cordis", kind: "插件运行时", role: "服务、上下文、依赖注入、类型化事件、可逆副作用。", note: "策略网关适合用 waterfall" },
  { name: "@deepseek-ai/dsh-sdk-client", url: "https://www.npmjs.com/package/@deepseek-ai/dsh-sdk-client", kind: "SDK", role: "stdio JSON-RPC 驱动 DSH 子进程，含 turns API 与 HarnessClient。", note: "适合平台后端调度" },
  { name: "@deepseek-ai/dsh-sandbox", url: "https://www.npmjs.com/package/@deepseek-ai/dsh-sandbox", kind: "沙箱契约", role: "ctx.sandbox 抽象与 SandboxProvider 契约，接入容器/微虚机/K8s。", note: "权限仍需外部强制" },
  { name: "@deepseek-ai/dsh-headless", url: "https://www.npmjs.com/package/@deepseek-ai/dsh-headless", kind: "无界面执行", role: "一次性 Agent/Session runner，不含 Host、HTTP、浏览器层。", note: "适合批处理与平台调度" },
  { name: "deepseek-ai/DeepInfer", url: "https://github.com/deepseek-ai/DeepInfer", kind: "官方推理框架", role: "DeepSeek-V4.1-Flash 高性能推理；支持 SM100 与昇腾 950。", note: "不含 KV cache/PD 分离/负载均衡" },
];

const phases = [
  ["0｜边界与基线", "1–2 周", "建立目标、预算、权限、基准仓库、结果 schema、沙箱和人工审批门。", "能从一个固定任务生成可追踪的 baseline run。"],
  ["1｜单任务自动实验", "2–4 周", "仿照 autoresearch：固定时间预算、固定评测、单一可修改面、Git 分支、保留/回退。", "连续运行 24 小时无重复提交；每轮有结果和 provenance。"],
  ["2｜资源编排", "4–8 周", "Temporal 总控；Slurm/HPC、Kubernetes/Kueue、SkyPilot 云资源适配；检查点和自动回收。", "worker、节点或网络故障后可恢复；闲置资源自动释放。"],
  ["3｜文献到复现", "6–10 周", "检索、去重、全文解析、方法卡、代码映射、baseline、三种子复现和差异报告。", "每个候选方法都有可执行复现计划和证据链。"],
  ["4｜软件工厂", "上游冻结后 8–12 周", "接入开源 Super-agent。Superpowers 做方法门禁，独立评审，本工程不自研路由器。", "合并候选通过单测、集成、E2E、安全和人工策略门。上游未冻结时走单工单降级。"],
  ["5｜研究组合与生产化", "3–6 个月", "多项目队列、研究组合、成本预测、失败分析、模型路由、报告和权限治理。", "从目标/计划表自动拆解，形成可审计的研究日报和周报。"],
];

const gates = [
  ["自动允许", "读公开文献、解析文件、创建分支、运行沙箱测试、申请预算内 CPU/GPU/HPC 任务、保存结果、生成报告草稿。"],
  ["必须审批", "真实量子硬件或昂贵超算任务、外发专有数据、修改基础设施、合并主分支、发布论文/报告、变更配额或安全策略。"],
  ["硬性禁止", "直接获得长期云密钥、直接修改生产环境、上传任意脉冲/控制指令、无限循环无预算、在执行状态未知时盲目重试。"],
];

const queues = [
  ["CPU 快速验证", "单测、语法、静态检查、文献抽取", "分钟级", "失败重试；不占 GPU/HPC"],
  ["GPU 短实验", "小数据、超参探索、代理评测", "5–30 分钟", "固定预算；自动 stop/autostop"],
  ["HPC 长任务", "大规模训练、模拟、复现和扫描", "小时–天", "提交前检查点；完成/失败都回收"],
  ["真实算法后端", "真实 QPU、实验设备或高成本服务", "按供应商", "人工策略门；执行未知时禁止重复"],
  ["浏览器与发布", "前端 E2E、截图、报告渲染", "分钟级", "隔离浏览器上下文；保留 trace"],
];

function ProjectMatrix() {
  const [category, setCategory] = useCanvasState("project-category", "全部");
  const rows = useMemo(
    () => projects.filter((project) => category === "全部" || project.category === category),
    [category],
  );

  return (
    <Stack gap={12}>
      <Row align="center" gap={12} wrap>
        <Text weight="semibold">项目矩阵</Text>
        <Select value={category} onChange={setCategory} options={categoryOptions} />
        <Text size="small" tone="secondary">当前显示 {rows.length} / {projects.length} 个候选项目；项目角色是架构建议，不是全部功能承诺。</Text>
      </Row>
      <Table
        headers={["类别", "项目", "可复用能力", "研究信号", "建议"]}
        rows={rows.map((project) => [
          project.category,
          <Link href={project.url}>{project.name}</Link>,
          project.role,
          project.signal,
          project.decision,
        ])}
        columnAlign={["left", "left", "left", "left", "left"]}
        stickyHeader
        striped
      />
    </Stack>
  );
}

function Overview() {
  return (
    <Stack gap={18}>
      <Callout tone="warning" title="先定义可控自治，再追求 24 小时无人运行">
        24/7 的正确实现是持久化工作流、租约、检查点、预算、沙箱和告警组成的控制系统，而不是让一个代理进程运行无限 shell 循环。真实硬件、昂贵资源、外发数据、生产合并和正式发布必须保留策略门。
      </Callout>

      <H2>四个图片项目应如何组合</H2>
      <Table
        headers={["图片项目", "应保留的核心思想", "不应直接照搬的部分"]}
        rows={[
          ["Superpowers", "把需求澄清、设计、计划、TDD、审查和收尾做成技能与方法层。", "不要把技能触发当作权限控制；权限必须在服务端策略层执行。"],
          ["Karpathy autoresearch", "固定实验预算、固定指标、固定修改面，让每轮结果可比较。", "它是单 GPU/单任务原型；不能直接承担多租户 HPC、昂贵硬件和复杂回滚。"],
          ["Ralph", "实验尝试每轮使用新上下文，状态放在 Git、清单和平台记录里。", "编码循环改由上游 Super-agent 承担，不落地 while true。"],
          ["Pi coding agent", "最小、可扩展的 Agent harness，技能、扩展、RPC 和 SDK 可组合。", "本项目用 DeepSeek Harness 承接该层；Pi 只作为最小化设计参照。"],
        ]}
        striped
      />

      <H2>推荐的最小可行组合</H2>
      <Grid columns={2} gap={12}>
        <Card>
          <CardHeader>控制与资源层</CardHeader>
          <CardBody>
            <Text><strong>Temporal</strong> 负责长流程、计时器、重试和外部回调；<strong>PostgreSQL</strong> 保存状态；对象存储保存代码、数据、日志、检查点和结果；<strong>OpenTelemetry</strong> 贯穿代理、调度器、实验和前端。</Text>
            <Text><strong>Slurm</strong> 管 HPC；<strong>Kueue</strong> 管 Kubernetes 配额与队列；<strong>SkyPilot</strong> 管云/GPU 多基础设施；真实算法后端通过独立 adapter 和 lease 接入。</Text>
          </CardBody>
        </Card>
        <Card>
          <CardHeader>代理与研究层</CardHeader>
          <CardBody>
            <Text><strong>DeepSeek Harness（Cordis 插件）</strong> 作为统一 Agent Harness；<strong>上游 Super-agent</strong> 作为编码协作运行时；<strong>Superpowers</strong> 作为方法门禁；<strong>autoresearch</strong> 作为固定预算实验协议。实验尝试仍由 Temporal 启动新上下文。</Text>
            <Text><strong>STORM/Open Deep Research</strong> 做检索规划，<strong>PaperQA</strong> 做带证据问答，<strong>GROBID + Marker/MinerU</strong> 做文献解析，<strong>DVC + MLflow + Optuna/Ax</strong> 做数据、实验和搜索管理。</Text>
          </CardBody>
        </Card>
      </Grid>

      <H2>系统必须有的七个闭环</H2>
      <Table
        headers={["闭环", "输入", "自动动作", "产出"]}
        rows={[
          ["目标闭环", "目标/计划表、预算、期限、研究方向", "拆成可验证任务、优先级和资源约束", "Goal、Milestone、ResearchTask"],
          ["文献闭环", "关键词、引用图、PDF、代码链接", "检索、去重、解析、抽取方法卡和差距", "EvidenceGraph、MethodCard"],
          ["复现闭环", "论文方法卡、数据和基线", "环境锁定、实现、单测、三种子运行、差异分析", "ReproductionReport"],
          ["新想法闭环", "文献差距、失败结果、历史实验", "提出假设、估计成本、设计消融和停止条件", "Hypothesis、ExperimentSpec"],
          ["算法实验闭环", "ExperimentSpec、代码分支、预算", "申请资源、运行、回收、分析、保留或回退", "Result、Decision、Checkpoint"],
          ["软件工程闭环", "Issue/需求、代码库、验收标准", "计划、实现、单测、E2E、静态安全、审查、PR", "Patch、TestEvidence、ReleaseCandidate"],
          ["知识回流闭环", "实验结果、审查意见、负结果", "更新方法卡、失败库、提示和下一轮计划", "ResearchMemory、日报、周报"],
        ]}
        striped
      />
    </Stack>
  );
}

function Architecture() {
  return (
    <Stack gap={18}>
      <H2>建议的分层架构</H2>
      <Table
        headers={["层", "职责", "关键对象", "边界"]}
        rows={[
          ["L0 目标与组合", "管理你的长期目标、计划表、里程碑、预算和优先级。", "Goal、Milestone、Portfolio", "只提出任务，不直接调用计算资源。"],
          ["L1 研究代理", "检索、阅读、提出假设、选择复现路线、撰写研究摘要。", "PaperRecord、Claim、MethodCard、Hypothesis", "只能通过工具契约读取证据和提交计划。"],
          ["L2 工程代理", "实现算法、重构代码、写测试、处理失败和生成 PR。", "PatchPlan、Branch、TestEvidence、PR", "只能在临时 worktree/容器内修改；不能直接推生产。"],
          ["L3 实验编译器", "把研究假设编译为可执行实验，生成资源需求、停止条件、随机种子和预算。", "ExperimentSpec、ResourceRequest、AcceptanceTest", "拒绝无指标、无基线、无上限的实验。"],
          ["L4 资源控制面", "申请、排队、启动、监控、检查点、回收和对账 CPU/GPU/HPC/云/真实后端。", "Lease、Run、Attempt、UsageRecord", "代理不能持有长期凭据；执行未知时禁止盲重试。"],
          ["L5 证据与评测", "保存代码、数据、环境、日志、指标、统计和结论的可追溯关系。", "Artifact、Provenance、Metric、Decision", "发布结论前必须通过证据完整性门。"],
          ["L6 人机治理", "审批高风险动作、处理不确定执行、预算和安全事件。", "Approval、PolicyDecision、Incident", "自动化的边界由服务端强制，不由提示词决定。"],
        ]}
        striped
      />

      <H2>运行时状态机</H2>
      <Table
        headers={["阶段", "必须发生", "失败时的正确动作"]}
        rows={[
          ["计划", "校验目标、预算、权限、数据地域、截止期和验收指标。", "回到计划阶段；不申请计算资源。"],
          ["准备", "创建分支/worktree、锁定环境、构建镜像、登记输入 artifact。", "清理临时资源，保留错误与构建日志。"],
          ["预检", "运行静态检查、单测、基线 smoke、资源估计和成本预估。", "阻止昂贵运行，要求代理修复或人工调整。"],
          ["排队", "生成带幂等键的 ResourceRequest，获取短期 lease，等待资源就绪。", "持久等待；不占用无效的 GPU/HPC 节点。"],
          ["执行", "写入 attempt 后提交；持续心跳、日志、指标和检查点。", "先对账是否执行；未知状态进入人工/延迟对账。"],
          ["分析", "读取原始结果、重算指标、比较基线和置信区间。", "标记失败或部分结果，不把代理解释当成科学结论。"],
          ["决策", "按预先规则保留、回退、扩展消融或停止。", "更新失败库和停止原因，避免重复无效搜索。"],
          ["回收", "释放节点、GPU、容器、临时文件、短期 token 和 lease。", "告警并执行幂等补偿；不得因回收失败无限续租。"],
        ]}
        striped
      />

      <H2>资源队列与回收策略</H2>
      <Table
        headers={["队列", "适用任务", "运行上限", "回收/重试"]}
        rows={queues}
        striped
      />
    </Stack>
  );
}

function DSHPlatform() {
  return (
    <Stack gap={18}>
      <H2>DeepSeek Harness 在公司平台中的位置</H2>
      <Text tone="secondary">
        DSH 是统一 Agent Harness，负责会话、工具、模型适配、技能、插件与执行轨迹。它不承担跨天长流程状态、资源所有权、租户计费与最终权限边界；这些由外部持久工作流、资源调度器和策略层负责。
      </Text>

      <Table
        headers={["官方组件", "类型", "可复用能力", "使用注意"]}
        rows={dshStack.map((item) => [
          <Link href={item.url}>{item.name}</Link>,
          item.kind,
          item.role,
          item.note,
        ])}
        columnAlign={["left", "left", "left", "left"]}
        striped
      />

      <H2>职责切分</H2>
      <Table
        headers={["能力", "DSH", "外部系统"]}
        rows={[
          ["多轮会话、上下文", "负责", "持久工作流只记录业务状态"],
          ["工具调用与插件", "负责", "策略层负责允许/拒绝"],
          ["模型适配与流式输出", "负责", "模型网关负责配额、成本、回退"],
          ["跨天/跨月任务恢复", "不负责", "Temporal 负责"],
          ["CPU/GPU/HPC/云调度", "不负责", "Slurm / Kueue / SkyPilot 负责"],
          ["租户、预算、计费", "不负责", "平台控制面 + PostgreSQL 负责"],
          ["代码/数据/实验证据链", "不负责", "对象存储 + MLflow + DVC 负责"],
          ["高风险动作最终许可", "不负责", "策略引擎 + 人工审批负责"],
        ]}
        striped
      />

      <H2>插件落位</H2>
      <Table
        headers={["公司插件", "服务键", "职责"]}
        rows={[
          ["goal", "ctx.goal", "目标、计划表、里程碑、任务草案"],
          ["literature", "ctx.literature", "检索、去重、解析、方法卡"],
          ["evidence", "ctx.evidence", "证据登记、定位、引用一致性"],
          ["experiment", "ctx.experiment", "实验规格编译、校验、决策"],
          ["resource", "ctx.resource", "资源申请、续租、释放、对账"],
          ["software", "ctx.software", "worktree、补丁、测试、审查、PR"],
          ["policy", "事件监听", "高风险动作拦截与审批"],
          ["memory", "ctx.memory", "研究记忆、失败库"],
          ["report", "ctx.report", "日报、周报、复现报告"],
          ["observability", "事件监听", "trace、指标、审计"],
        ]}
        striped
      />

      <Callout tone="warning" title="Harness 不是安全边界">
        DSH 的插件可扩展性不等于权限隔离。所有高风险工具必须通过平台网关，所有执行必须在分级沙箱内，所有长期密钥必须由凭据代理签发短期 token。DSH 官方标注为 public preview，正式开发前必须锁定版本并保留适配层。
      </Callout>
    </Stack>
  );
}

function Roadmap() {
  return (
    <Stack gap={18}>
      <H2>分阶段实施路线</H2>
      <Table
        headers={["阶段", "周期", "实施重点", "退出标准"]}
        rows={phases}
        striped
      />

      <H2>验收指标建议</H2>
      <Table
        headers={["维度", "初始目标", "如何测量"]}
        rows={[
          ["流程可靠性", "控制面月度可用性 ≥ 99.5%；worker 重启后 ≥ 95% 工作流可恢复。", "故障注入：杀 worker、断网、重启编排服务、延迟回调。"],
          ["副作用安全", "物理/昂贵执行的重复执行检测为 0；未知执行不自动重提。", "按 submission token、attempt、provider job ID 和账单对账。"],
          ["资源效率", "长任务完成后 5 分钟内释放临时资源；无效 GPU/HPC 等待占比 < 10–15%。", "统计 lease、分配、等待、执行和回收时间。"],
          ["实验可信度", "每个正式结论都有 baseline、对照、种子、环境、指标定义、原始结果和 provenance。", "自动检查 ResultManifest 和 EvidenceGraph。"],
          ["算法质量", "候选改进至少通过独立复核集或多种子稳定性门，再进入昂贵资源。", "效果均值、置信区间、方差、成本和失败率联合判定。"],
          ["软件质量", "合并候选必须通过单元、集成、浏览器 E2E、静态安全和依赖扫描。", "pytest/Hypothesis/Testcontainers/Playwright/CodeQL 或 Semgrep/Trivy。"],
          ["文献质量", "发布的综述或方法卡有可解析来源、定位证据和引用一致性。", "来源 URL、版本、页码/章节、抽取片段和人工抽查。"],
        ]}
        striped
      />

      <H2>首个 30 天执行清单</H2>
      <Table
        headers={["时间", "任务", "交付物"]}
        rows={[
          ["第 1–3 天", "确定一个最小研究问题、一个 baseline、一个指标和一个最大预算。", "Research Charter + baseline run"],
          ["第 4–7 天", "搭建代理沙箱、Git worktree、结构化 artifact、日志和结果 schema。", "可恢复的单轮 ExperimentSpec"],
          ["第 2 周", "实现固定时间实验循环：修改→预检→运行→评测→保留/回退→记录。", "24 小时模拟循环；无真实昂贵资源"],
          ["第 3 周", "接入一个 HPC/云适配器，完成申请、排队、检查点、结果回传和自动回收。", "一次完整长任务闭环"],
          ["第 4 周", "接入文献检索与 PDF 解析，产出 10–20 个方法卡，并挑 1 个做复现。", "第一份 ReproductionReport + 失败分析"],
        ]}
        striped
      />

      <Callout tone="info" title="技术选型的收敛规则">
        第一版不要同时部署 Temporal、Prefect、Airflow、Dagster、Flyte、Argo 和多个 Agent harness。控制面只选 Temporal；编码协作接入上游 Super-agent，不并行部署 OpenHands、Pi 或其他编码代理。实验用 DVC/MLflow；HPC 用 Slurm；Kubernetes 用 Kueue；云 GPU 用 SkyPilot。Harness 统一使用 DeepSeek Harness。
      </Callout>
    </Stack>
  );
}

function App() {
  const theme = useHostTheme();
  const [view, setView] = useCanvasState("view", "overview");

  return (
    <div style={{ background: theme.bg.editor, color: theme.text.primary, minHeight: "100vh", padding: 24 }}>
      <Stack gap={18}>
        <Row align="start" justify="space-between" gap={16} wrap>
          <Stack gap={6} style={{ maxWidth: 780 }}>
            <H1>DeepSeekHarness 企业级自主研发与自动科研平台</H1>
            <Text tone="secondary">基于公开网络与 GitHub 的调研。研究口径：2026-10-29；计划修订：2026-11-01。{projects.length} 个生态项目，外加 {dshStack.length} 个 DSH 相关组件。编码协作按 Super-agent 五模块开源假设修订。</Text>
          </Stack>
          <Row gap={8} wrap>
            <Stat value={projects.length} label="生态项目" tone="info" />
            <Stat value={dshStack.length} label="DSH 官方组件" />
            <Stat value="7" label="必须闭环" />
            <Stat value="6" label="实施阶段" />
          </Row>
        </Row>

        <Divider />
        <Row gap={8} wrap>
          <Pill active={view === "overview"} onClick={() => setView("overview")}>总览与组合</Pill>
          <Pill active={view === "dsh"} onClick={() => setView("dsh")}>DSH 平台层</Pill>
          <Pill active={view === "architecture"} onClick={() => setView("architecture")}>架构与运行时</Pill>
          <Pill active={view === "projects"} onClick={() => setView("projects")}>78 项目矩阵</Pill>
          <Pill active={view === "roadmap"} onClick={() => setView("roadmap")}>路线与验收</Pill>
        </Row>

        {view === "overview" && <Overview />}
        {view === "dsh" && <DSHPlatform />}
        {view === "architecture" && <Architecture />}
        {view === "projects" && <ProjectMatrix />}
        {view === "roadmap" && <Roadmap />}

        <Divider />
        <H2>自治边界与治理门</H2>
        <Table
          headers={["级别", "规则"]}
          rows={gates}
          rowTone={["success", "warning", "danger"]}
          striped
        />
        <Text size="small" tone="tertiary">来源：每个项目名称链接到其官方 GitHub 仓库；项目状态、README 能力和许可信息应在正式采购或生产部署前按 commit/tag 再次核验。该画布是架构决策材料，不是对任何项目 SLA、科学结论或硬件能力的保证。</Text>
      </Stack>
    </div>
  );
}

export default App;
