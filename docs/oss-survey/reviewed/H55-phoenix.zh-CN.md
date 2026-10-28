# H55 Phoenix：OTel 注册与分区许可复核

- 项目：`arize-ai/phoenix`。
- SHA：`33ed20ad89a787f971145a470f690566217cace6`，提交 2026-10-21T21:14:17+00:00。
- 来源：`/tmp/oss-arize-ai-phoenix`。
- 验证：静态源码和单元测试阅读；未启动 collector。

## 许可的关键修正

根 `LICENSE:1-14` 为 Elastic License 2.0，包含向第三方提供 substantial functionality 的 hosted/managed service 限制。不能把整个 Phoenix 主体写作 Apache-2.0。

独立 `packages/phoenix-otel/LICENSE:1-10` 为 Apache-2.0。因此“仅用埋点包”和“嵌入/对外托管 Phoenix 平台”不是相同许可范围。具体使用方式仍需合规审查，本文不作法律保证。

## 调用链

`phoenix.otel.register()` 接收 endpoint、project_name、batch、headers、protocol、auto_instrument 和 api_key。
它建立 TracerProvider，再配置简单或批量处理器以及 HTTP/gRPC exporter；用户可选择不设置全局 tracer provider。
环境变量可以提供 collector 与 project，不传 endpoint 不等于不出网。
证据：`packages/phoenix-otel/src/phoenix/otel/otel.py:25-32,37-105`。

## 三个实现重点

1. `OTLPTransportProtocol._missing_()` 对不合法协议明确报错，对 None 走推断；HTTP 字符串拼错会给出具体建议，不静默换协议。
2. `register` 的 `batch=False` 默认使用 SimpleSpanProcessor；这与“都是异步队列”的笼统理解不同。batch 模式可选，但也不保证审计可靠性。
3. 默认 `set_global_tracer_provider=True` 影响进程全局；DSH 内已有 instrumentation 时应避免多个组件争抢全局 provider。`auto_instrument=False` 默认不自动挂全体库，但开启后数据范围需复核。

```65:74:packages/phoenix-otel/src/phoenix/otel/otel.py
def register(
    *,
    endpoint: Optional[str] = None,
    project_name: Optional[str] = None,
    batch: bool = False,
    set_global_tracer_provider: bool = True,
    headers: Optional[Dict[str, str]] = None,
    protocol: Optional[Literal["http/protobuf", "grpc"]] = None,
    verbose: bool = True,
    auto_instrument: bool = False,
```

这些参数是 SDK 入口默认值，不是所有产品部署的默认设置。

## 测试证据

`packages/phoenix-otel/tests/test_otel.py:49-62` 断言默认一个 SimpleSpanProcessor、GRPCSpanExporter。
`:73-81` 断言 batch=True 改为 BatchSpanProcessor。
`:90-107` 检查不设置全局 provider 和自定义 HTTP endpoint。
这支持“配置会影响实际 exporter 形态”的结论，不证明传输可靠性和内部内容脱敏已满足公司标准。
测试只静态阅读，没有执行。

## 对公司边界

模型/工具 span 可用于性能与故障追踪，但不能代替用户授权、设备审批、作业事实或平台结算。
公司 provider/capability/asset 引用采用自有白名单字段；模型 request/response 完整内容不默认上报。
诊断导出失败不能触发 QPU 自动重试，unknown 状态仍向平台对账。

## 文件落点

- 在既有 `diagnostics.py` 的白名单事件出口评估 OTel 适配，先定义合同字段再编码。
- `runtime.js` 保留合同 digest 和执行状态，不从 trace UI 反推权限。
- `tests/` 增加 exporter endpoint 配置错误、全局 provider 冲突、导出失败不覆盖业务结果。
- 若对外开放 trace 查询，租户和内容授权要由服务端保证；不要直接公开内部 Phoenix 控制面。

## 结论与未验证范围

Phoenix 可作为观测候选，不与 Langfuse/AgentOps 默认叠装。优先复用 OTel 标准接口，保留可替换出口。
本篇没有审查 Phoenix 全部认证、保留策略、数据库和 UI API。根许可与独立包许可必须分开，以此修正旧稿的一行速评。

## 证据

`LICENSE:1-14`；`packages/phoenix-otel/LICENSE:1-10`；`packages/phoenix-otel/src/phoenix/otel/otel.py:25-32,37-62,65-105`；`packages/phoenix-otel/tests/test_otel.py:49-107`。
