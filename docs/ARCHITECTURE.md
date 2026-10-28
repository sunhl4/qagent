# Company Agent 目标架构

```text
DeepSeek Harness
  ├── company-agent-policy
  ├── company-agent-core
  │   ├── capability discovery
  │   ├── knowledge search
  │   └── workflow validation
  ├── company-agent-quantum
  │   ├── company-quantum-platform bridge
  │   ├── independent simulator bridge
  │   └── independent compiler bridge
  └── company-agent-device
      └── approved ionstack TwinRun bridge
```

## 责任边界

DSH 是运行时。Company Agent 是合同与治理层。`company-quantum-platform` 是科学算法真源。模拟器、编译器、设备和知识服务是独立 provider。

## 规划与检索能力的实现方式

- Planner/Criticizer → 结构化 workflow + deterministic validator。
- RAG/Advisor → 带来源和版本的知识检索。
- Guided/Tools 路由 → capability registry 与 provider resolution。
- Reviewer → schema、provenance、handle 和科学 provider 验证。
- Calibration Agent → 不迁移；设备约束留在设备服务并受人工批准。

## Provider bridge

所有南向服务接收：

```json
{
  "protocol": "company-agent-provider/1.0",
  "operation": "algorithm.run",
  "request_id": "req_0123456789abcdef0123456789abcdef",
  "payload": {"algorithm": "example", "component_version": "1.0", "catalog_version": "cat_example"}
}
```

成功返回（必须原样回传本次请求的 `request_id`）：

```json
{
  "protocol": "company-agent-provider/1.0",
  "ok": true,
  "provider": "company-quantum-platform",
  "request_id": "req_0123456789abcdef0123456789abcdef",
  "result": {"asset_id": "asset_example"}
}
```

失败返回同样携带 `protocol`、`provider`、`request_id`，令 `ok` 为 `false`，仅使用字符串 `error`，不得混入 `result`。Agent 不转发服务端错误正文，只返回固定的 provider 失败或 HTTP 状态信息。成功和失败信封均不允许额外字段。

`contracts/results.json` 定义模型可见的结果预算：紧凑 UTF-8 JSON 最多 64,000 字节；provider 结果另有限制嵌套深度、集合长度、字符串字节数以及禁止字段。超限或包含禁止数据时整次调用失败，不截断后伪装成功。DSH 的 schema 投影只剥离已知不支持的约束，Python 在调用前校验完整输入与输出 schema 定义。

Agent 不假定平台内部模块、类名、数据库或作业实现，也不 import `company_quantum`。算法身份是平台 `(component_id, component_version)`；内置组件与后续插件通过同一 `algorithm.catalog` 发现，运行同时绑定该响应的 `catalog_version`。目录声明不等于授权执行；平台侧须显式可信注册、机器参数合同、预算、admission 校验与独立执行授权，默认没有执行器。测试使用平台真实 HTTP 边界和无科学行为替身，运行时代码不跨仓导入。

## 调用一致性与执行结果未知

六个合同文件在每次调用开始时读为内容标识的不可变快照，完成定义和关联校验。发送服务请求前核对磁盘内容，变更时失败；快照在调用结束即释放，不复用人工批准。

诊断通过 stderr 的固定 `company-agent-diagnostic:` 短 JSON 元数据发送，CLI stdout 仍为唯一返回信封。只允许工具、操作、请求 ID、合同摘要、耗时、状态、错误类别和执行状态；不含凭据、URL、完整参数和科学正文。DSH 桥接仅接受封闭字段和合法枚举。

设备发送边界后的超时、断连、不可信结果或取消被保守标记为 `unknown`。POSIX 上 DSH 桥接为 CLI 建立独立进程组；取消、超时、输出超限会清理整组并对继承管道设置有界关闭。其他操作系统失败闭合。本地进程已清理不等于设备已停止。客户端自动重试次数为零；请求 ID 不是服务端幂等保证。没有合同外的状态查询工具，操作员须经服务方管理渠道核对原请求。

设备每次审批原因显示该次参数快照的 provider、circuit_id 和 shots；实际设备身份未经查询不会被编造。工作流可声明已有外部句柄并显式绑定来源，仍仅做静态校验，不引入执行循环。

版本化标量指标、工作流绑定、统一内容边界与诊断规则见 [2.0 迁移规范](contracts-2.0-migration.zh-CN.md)。真实验收入口复用受管 DSH 界面，不创建另一套执行循环或自动批准。
