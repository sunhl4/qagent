# Company Agent 续行完善与本地复验

任务 ID：AGENT-CONTINUATION-20261009。日期：2026-10-09。

## 授权、起点与范围

用户于 2026-10-09 09:25（UTC+8，会话时间戳）明确要求“去找昨天最后做的事情接着去做完善我们的 agent”，并要求执行既有计划、沿用已有待办、不编辑计划文件。本轮从 10 月 8 日最后交付 `closure-20261008-05` 接续，历史 587 项 Agent 测试、平台 46 项及 79 子测试、双仓 1 项仅作各自快照证据，不当作本轮结果。

上一段会话在收到延迟完成通知后，曾自行重开待办并写入 `docs/evidence/continuation-20261009-01/reproduce_boundaries.py` 与 `before.json`；当时没有新的实施授权，该行动属于范围扩张。本次明确续行授权从本条用户消息起生效，不追溯改变上述事实。保留原诊断，不删除或覆盖。该诊断通过替换函数观察校验调用顺序，不证明实际执行过恶意程序；pytest 环境继承及零测试进程判断是局部探针，不是全量验收。

本轮只完善既有计划 A–D 范围内的发布校验、验收完整性、独立证据和复验，不添加模型/会话/工具执行循环，不改工具及结果合同 2.0 或 provider 信封 1.0，不增加科学依赖或固定算法列表。DSH（DeepSeek Harness）仍是唯一运行时，11 个工具、三种科学句柄和逐次设备审批规则不变。平台科学实现及旧候选保持不动。

## A. 发布签认先于待验程序执行

`release_manifest.py verify` 原先先做内容及版本校验，再验证外部签认。版本校验会执行待验 Node，因此“无效签认阻止 DSH 启动”不足以证明“无效签认前没有执行待验程序”。

现将签认与信任路径作为 `verify_manifest` 的可选成对参数，基础清单及根路径检查后先验证 HMAC，再继续内容、权限、依赖身份与版本探测。验签和内容核对使用同一个解析对象，中间不重新读取清单。CLI 通过同一路径执行，配对参数缺失时提前拒绝。

永久回归包括无效签名、关联摘要不符、信任文件权限错误、单边参数缺失、签认后源码/Node 篡改和清单单次读取。实际 `start_runtime.sh` 的隔离测试给合成 Node 增加独立版本探测标记：有效签认仅进入替身；无效签认既不探测 Node，也不创建 preset 或启动替身。

边界：`create` 与未提供签认的开发校验仍需运行版本探测，只能用于已信任的本地材料。操作系统、校验器自身、Python 标准库、外部信任材料和只读挂载仍是信任前提；不声称解决同属主或高权限修改的竞态，也不证明真实生产部署。

## B. 独立离线验收与选择完整性

`verify_acceptance.py` 报告升级为 1.3；`offline_environment` 清除全部继承的 `PYTEST_*` 配置、关闭外部 pytest 插件自动加载和 Python 用户包目录。新增管理脚本 `acceptance_pytest.py`，固定使用项目配置和 `tests/`，覆盖配置里的 `addopts`，只允许按 `platform_compatibility` 标记排除双仓测试。

pytest 钩子记录完整收集集合、按唯一许可标记推导的应执行/应排除集合、实际选中/筛除集合以及每个用例 setup/call/teardown 的结果；同时要求每个 `test_*.py` 有收集项。通过新的排他临时 JSON 文件传回短计数与完整性证据，父进程使用有界严格读取器验证。本次不再从任意标准输出中的“passed”文本推断成功，不硬编码历史测试数量。收集后未执行、空测试文件、任意额外筛除、缺报告、计数或退出码不符、失败、xfail 等不能通过；普通跳过为 blocked。失败节点去除参数实例文本，断言正文与原始日志不进入短报告。

`record_closure.py` 另外核验本地子报告确有四个成功检查及正整数通过数，拒绝“退出 0 但报告缺失/不完整/失败”；平台和双仓文本计数也拒绝退出 0 却报告 failed 的矛盾结果。跨仓仍是独立门禁，不把排除数计作通过。新增包装器纳入发布清单，旧生产清单需重建并重新签认，不允许静默忽略新增受管文件。

永久回归使用真正 pytest 子进程与微型临时测试工程验证环境/配置筛选隔离、收集不执行、删除用例、空模块、skip/xfail/失败、参数脱敏以及结构化报告篡改。可信项目测试及其本地 `conftest.py` 仍属于输入信任范围；本机制防止误配置和不完整执行，不把同进程测试代码视作恶意代码沙箱。

## C. 环境与执行记录

昨天使用的 `/tmp/company-agent-dev/bin/python` 已不存在。新解释器为 `/tmp/company-agent-dev-20261009/bin/python`（系统 Python 3.12.3 的独立 venv）。仅从既有 pip HTTP 缓存恢复 16 个与 `runtime/python-dev.lock` SHA-256 一致的 wheel，执行 `pip install --no-index --only-binary=:all: --require-hashes`；`pip check` 通过。平台质量环境和系统/用户包未改变；依赖锁未修改。

恢复脚本及逐包摘要、命令和 freeze 见 `evidence/continuation-20261009-01/restore_environment.py`、[成功环境报告](evidence/continuation-20261009-01/offline-environment-03.json)。首次扫描只看首个 wheel tag，第二次又将 setuptools 内置 vendor 元数据误算为多个主包，两个前置 blocked 报告保留；修正扫描后全部缓存命中，没有安装替代版本或下载。

本轮两次独立委派均因环境的模型访问配置错误在启动时失败，未产生任何修改；全部实现、环境恢复和验证由主会话完成，未反复重试。初期启动行为探针仅用合成 Node，正反分支通过。部署、人工证据、验收与记录器五文件及新增结构化证据回归共 131 项通过（51.28 秒）。静态检查曾发现一处新行超过 110 字符，已修正；最终全量结果另记，定向结果不与全量相加。

首轮完整证据 [closure-20261009-01](evidence/closure-20261009-01/summary.json) 被正确拒绝：Agent 588 passed、28 failed、0 skipped、1 deselected，首尾输入一致；平台定向/质量、双仓与基准四组通过。原因是两份桥接/审批测试将解释器硬编码为已消失的 `/tmp/company-agent-dev/bin/python`，与验收进程实际使用的新环境不同。改为 `Path(sys.executable)`，桥接 Node 路径同步使用 `COMPANY_AGENT_RUNTIME_DIR` 或用户缓存约定，消除用户名硬编码，不创建旧路径假环境、不降低断言。28 项回归全部通过（18.59 秒），70 个受管源文件静态检查通过。

修正后在新的 [closure-20261009-02](evidence/closure-20261009-02/summary.json) 目录重跑完整五组，全部通过。首轮失败证据不覆盖，其他四组的通过也不与后续 Agent 结果拼接；最终采用本次完整运行及首尾稳定身份。

### 最终实测结果

主机 UTC 运行区间为 2026-10-09 02:38:58 至 02:44:21（UTC+8 为 10:38:58 至 10:44:21）；单调耗时单独记录，不能用二者相减替代。

- Agent：**616 passed、0 failed、0 skipped、1 deselected**；35 个测试文件全部收集，共 617 项，实际选中并完成 616 项，唯一排除项属于独立双仓门禁。测试进程 159.141 秒。
- Agent 静态：70 个受管源文件通过；DSH 六个合法组合及两个非法最小组合的拒绝检查通过，组合进程 103.544 秒；十个固定模型审批场景包含在 616 项内。
- 平台定向：**46 passed、79 subtests passed**，零失败/跳过/筛除，仅 provider、依赖别名、打包平台三文件；未执行科学全量套件。
- 平台质量：Ruff、151 文件 strict mypy、137 模块依赖检查通过。平台源码及测试本轮未改。
- 独立双仓：**1 passed**，零跳过/筛除，使用实际平台 HTTP 适配器与无科学行为执行替身。
- 十次独立基准通过，逐次样本保存。五组外层单调耗时依次为 272.227、6.002、26.280、2.489、8.982 秒。

原始证据：[本地短报告](evidence/closure-20261009-02/agent_local.log)、[平台测试](evidence/closure-20261009-02/platform_tests.json)、[双仓](evidence/closure-20261009-02/dual_repository.json)、[基准样本](evidence/closure-20261009-02/benchmark.log)。

### 身份与复现

`inputs_stable=true`，运行前后内容、文件集合和模式一致。Agent 枚举输入摘要 `sha256:4859cd2dadc5599e10f42bb5d75c471679bf597fab6752b3b4ffafd5a8128d7a`；平台 `sha256:8ec36eac5a575001e84678ec70054284dd4124b3e36fb47e2380e44c32ef89c2`，与昨天最终平台摘要相同。合同和组合锁摘要仍为 `sha256:f3c3fa774a3cbb31099b470841d02dd430fa2750f7733d0cf9a6acb59781cbe9`、`sha256:2d3a6cd9775f150fa0bf19edb737314d2db4949f2e12a5bc346ca20c08941b7f`。

在 Agent 根使用 `/tmp/company-agent-dev-20261009/bin/python scripts/record_closure.py --platform-source /home/sunhl/projects/company-quantum-platform --platform-python /home/sunhl/next03-envs/quality-py312/bin/python --output /absolute/new-evidence-directory` 复现；输出目录必须不存在，全部依赖须已安装。新解释器仅改变路径，Python 为 3.12.3，锁定 pytest 9.1.1、Ruff 0.16.9、build 1.6.1、Hypothesis 6.168.3。平台仍为 Python 3.12.14/Ruff 0.16.7/mypy 1.20.2。未重建或晋级平台发行工件。

README 和源码修改均先于最终运行；之后只更新文档与外部看板。源码清单不包含文档、缓存或已安装依赖，不代表主机冻结，不证明运行中无瞬时变化。开发依赖恢复报告及生产发布清单分别覆盖各自身份边界。

### 基准解释

六组“中位数 / nearest-rank 第 95 百分位”，单位毫秒：Python 启动 11.588 / 12.940；合同读取 4.569 / 7.356；逐次读取本地调用 102.339 / 169.865；调用内快照 37.986 / 51.697；回环 provider 85.936 / 131.360；冷 Node→Python CLI→回环 275.376 / 424.438。

12 篇合成文档、16 问题的召回和平均倒数排名仍为：空格切词 0.4286，中文双字切分 1.0；无结果准确率均为 1。逐问题延迟中位数分别 74.936 / 65.809 毫秒。十次样本的第 95 百分位就是最大值；顺序样本、主机负载未隔离，不能据此声称稳定提速，更不能当作模型/完整会话延迟或真实业务质量。

## D. 外部验收保持独立

`release_accepted=false`、`production_authorized=false`、`external_acceptance=blocked`。真实模型与科学服务、业务语料、浏览器审批观测、设备执行计数/未知结果对账、完整实际生产依赖、用户隔离及发行治理需另行授权和独立证据。本轮不下载、不访问真实凭据、不运行科学或设备任务、不提交、不重启用户运行时，不晋级平台候选 10。
