# ADR 0001：DeepSeek Harness 是唯一 Agent Runtime

状态：已接受。

公司主 Agent 直接建立在 DSH 上，不维护自研模型循环、会话循环或工具循环。公司代码只提供合同、策略、capability pack 和 provider bridge。

规划、知识检索、能力路由和验证作为确定性能力与量子 capability pack 实现，而不是第二套 runtime。
