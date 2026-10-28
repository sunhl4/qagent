# Ollama 调研更新入口

请阅读 [50 — Ollama 源码复核](reviewed/README.zh-CN.md#project-50)。chat、tools、模型能力、云代理与请求日志按实际实现和测试核对。

明确更正：generate 中 `genTruncate` 传入提示组装路径，不是模型输出 token 预算。公司已有模型部署，Ollama 是候选而非必须迁移目标；服务能力标签不能替代工具调用实测。见 [模型与前端汇总更新](F-汇总-前端与本地模型网关.zh-CN.md)。
