# 合同 1.2 与上线验收迁移说明

日期：2026-09-29。当前工具合同为 `1.3.0`，结果策略为 `1.1.0`，`company.algorithm` 为 `company.algorithm/1.2`，其余六项能力仍为 `/1.1`。provider 传输协议仍为 `company-agent-provider/1.0`。1.3 在 1.2 的 11 个工具之上新增 `quantum_algorithm_catalog`，三种科学句柄不变。升级合同、Python 和 DSH 插件必须一起部署，之后由运维重启 Runtime；旧会话不会自动刷新注册缓存。

## 合同 1.3 算法目录

算法真源是 `company-quantum-platform` 的组件目录与插件机制。Agent 不复制算法实现，不 import 科学包，也不在知识库维护算法名单。发现必须调用 `quantum_algorithm_catalog`（`algorithm.catalog`），执行必须调用 `quantum_algorithm_run`（`algorithm.run`）。`id` 对应平台 `component_id`（例如 `solver.vqe`），并携带平台 `maturity`（`reference/experimental/production`）与 `runnable`。目录新增条目不自动变成执行入口；只有 `runnable:true` 才可运行。后续重构算法和插件算法只要出现在平台目录中即可被识别，Agent 无需新增工具或改代码。

目录结果必需 `catalog_version`、`provider`（常量 `company-quantum-platform`）、`algorithms` 和 `complete`。条目按 `id` 升序且唯一；`id` 为小写有界标识。`complete:true` 不得带 `next_cursor`；部分页必须提供 `next_cursor`。参数指导是有界名称、类型、是否必填和短描述，不是可执行科学 schema。禁止把 `__list_algorithms__` 一类哨兵交给 `quantum_algorithm_run`。

平台未配置 `COMPANY_QUANTUM_PLATFORM_INVOKE_URL` 或 `COMPANY_QUANTUM_PLATFORM_TOKEN` 时，目录与运行都必须诚实失败，不得回落到本地名单。平台侧须实现 `algorithm.catalog`；本仓回环测试证明新标识可被发现并用于 `algorithm.run`，不代替真实平台验收。

## 封闭摘要

所有提供 `summary` 的操作只接受下列可选字段，未知字段导致整次结果失败。没有摘要时可省略 `summary`，也可返回空对象。

- 共通字段：`status` 只能为 `queued/running/completed/failed`；`duration_ms` 为 0 至 1,000,000,000 的有限数字，单位毫秒。
- `algorithm.run`、`circuit.export` 额外允许 `qubits`（1 至 1,000,000 的整数）与 `gate_count`（0 至 1,000,000,000 的整数）。
- `circuit.compile-estimate` 额外允许 `gate_count`、`depth`（均为 0 至 1,000,000,000 的整数）；顶层 `makespan_ns` 保持纳秒单位。
- `asset.get`、`circuit.simulate`、`device.identity`、`device.run` 仅接受共通摘要字段。`asset.list` 保持有界资产列表，没有任意摘要。
- 布尔值不是数字。`metrics`、任意文本、额外嵌套对象均不允许。现有顶层有界标签/状态字段不意味着可以放入秘密；服务端仍须审计这些字段。

可接受的算法结果为 `{"asset_id":"asset_example","summary":{"status":"completed","duration_ms":12.5,"qubits":2}}`。

拒绝示例：`{"asset_id":"asset_example","summary":{"metrics":{"energy":-1.1}}}`；`{"asset_id":"asset_example","summary":{"message":"arbitrary text"}}`；`{"asset_id":"asset_example","summary":{"duration_ms":true}}`。能量等科学指标若将来确需展示，先为对应操作定义名称、单位、范围和测试，再升级合同，不能恢复开放摘要。

禁止字段检查、明显科学正文检查和紧凑 UTF-8 JSON 的 64,000 字节预算继续作为第二层防护。系统不宣称能识别所有普通字符串中的秘密，非法结果也不会经删字段后伪装成功。

## 多分支静态工作流

`needs` 和 `produces` 仍表示三种句柄类型；新增 `bindings` 指定具体上游步骤。它是规划元数据，不是第四种科学句柄。

例如某个模拟步骤可声明 `needs:["circuit_id"]` 和 `bindings:{"circuit_id":{"step":"export_a","output":"circuit_id"}}`。不同算法或导出步骤可同时产生 `circuit_id`，但消费步骤必须明确选择来源。省略 binding 的旧格式仅在该类型已有且只有一个上游生产步骤时兼容。

拒绝来源歧义、自引用、未来步骤、类型不匹配、未声明输出，以及不属于指定设备 provider 的 `twin_id`。句柄不能重复出现在静态 `arguments` 中。输出每一步保留解析后的 `bindings`。

`valid:true` 和 `validation_scope:"structure_and_arguments_only"` 只表示结构和参数通过检查，不表示 provider 已配置、当前 preset 可执行、资产实际存在或用户已经批准。校验器不执行步骤、不调用科学服务，也不兑换批准。

## 知识检索完整性

搜索结果新增必需的 `scan` 对象：`complete`、`reasons`、`entries`、`files`、`bytes`。原因只用 `entry_budget/file_budget/byte_budget/depth_limit/oversized_file/read_error/changed_file/metadata_limit` 八个固定枚举，不含绝对路径。

`hits` 最多八条与部分扫描是不同概念：完整扫描找到二十条而只返回八条时，`complete` 仍为 true；因预算或异常漏扫时为 false，即使没有命中也不能断言资料不存在。来源是受管根内相对路径，版本是原始内容 SHA-256。

中文检索采用经固定样例评测的轻量词项方法，不是向量或语义检索；评测方法和结果见 `docs/performance-2026-09-29.zh-CN.md` 与基准脚本输出。

## 诊断、超时和合同身份

CLI stdout 保持唯一 JSON 信封；stderr 的 `company-agent-diagnostic:` 行仅包含固定字段：版本、事件、工具、操作、请求 ID、合同摘要、耗时毫秒、状态、错误类别、执行状态。DSH 仅转发校验后的元数据，丢弃任意 stderr 正文。每条 JSON 最多 2,000 字节，无凭据、地址、参数和科学正文。

合同快照只在单次调用内存在，包含六个合同文件的内容 SHA-256 身份。每次调用重新读取并验证，发送外部请求前再次核对内容；快照不跨调用复用，也不缓存人工批准。合同改变时新的调用必须重新校验。

`not_dispatched` 表示未进入发送边界；`dispatched` 是即将进入网络发送的保守记录，不是设备已收到的证明。发送边界之后若超时、断连、取消或返回不可信结果，则设备执行结果为 `unknown`。`completed` 表示收到并验证了响应，不承诺顶层科学状态已经完成。客户端取消只终止等待及本地 Python 子进程，不能声称设备停止。

开始诊断无法写出时，在发送前失败；结束诊断写出失败不得把已知返回结果改写为另一结果。DSH 超时/取消要等子进程退出和管道关闭后才结束本地调用，同时保留请求关联和未知结果提示。

## 设备服务接入验收要求

设备请求自动重试次数固定为零。`request_id` 当前仅为关联标识，**不是幂等键保证**。每次新调用生成新的 ID，重复提交新 ID 可能导致第二次实际执行。

服务接入方须在隔离验收环境提供以下证据：

1. 在接收任务与触发设备执行前持久记录请求 ID、调用身份、规范化输入摘要、接收时刻和服务内部执行关联；日志和审计接口不得向模型泄露底层正文。
2. 给出重复 ID 与不同输入冲突的服务行为规范、保留期限和原子性保证。若承诺幂等，需证明并发重复请求不会触发二次执行，不能仅靠客户端 ID 推断。
3. 模拟服务已接收但响应超时、断连以及客户端取消。客户端计数必须恰好一次且不重试；操作员按原始请求 ID 查询服务审计，记录未接收、执行中、成功、失败或仍未知。
4. 在结果仍未知时停止后续执行，先完成人工状态核对，再决定是否发起新审批。拒绝审批零调用、一次允许一次调用，第二次仍重新审批。
5. 校验认证失败、原样回传请求 ID、仅返回 `twin_id` 和 `qccd-twin` 来源、实际 shots 不超过请求、封闭摘要、短结果及错误正文隔离。

当前合同没有状态查询操作，本工程没有新增 `device.status` 或模型可见运维工具；核对由服务方既有管理渠道完成。上述服务端持久化与幂等证明属于外部验收，本地假服务通过不能替代。

## 统一验收入口

`python scripts/verify_acceptance.py` 默认只运行离线和回环测试、静态检查、真实 DSH 本地生命周期、六组合装配及检索基准，输出短 JSON。总状态区分 `passed/failed/blocked`；缺运行时、依赖或跳过必要测试不能被记录为通过。

真实模式使用 `--mode real`，只做配置预检并生成监督式验收用例，不发送真实服务请求。需要可用模型凭据、四类服务配置以及 `--asset-id`、`--circuit-id`、`--algorithm`。显式加 `--launch` 后以隔离临时状态目录和独立回环端口启动既有完整 DSH 界面；由操作员按输出用例提问、检查结果和逐次审批设备。脚本不自动提交提示、不设置批准标记、不将界面退出记为科学验收通过。

真实模式始终保留业务检查为 blocked，直到团队在受管验收记录中完成可审计的模型任务效果、服务合同和设备核对证据；配置存在只表示预检通过。此次实施没有运行真实模式或真实服务。
