# Langfuse 调研更新入口

请阅读 [54 — Langfuse 源码复核](reviewed/README.zh-CN.md#project-54)。认证 Session、TraceSession、观测存储、OTel 入口、评估与许可按具体代码分别核对。

Trace 不是合规审计或业务账单的自动替代。队列、采样及写入失败语义需独立设计；span 大小上限不等于进入模型前的短结果限制。商业模块归属也不能由功能目录名推断。见 [本地架构对照](03-本地架构对照与工程边界.zh-CN.md)。
