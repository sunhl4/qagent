# LangGraph 调研：已更新为固定版本复核稿

请阅读 [项目 37：LangGraph 源码复核](reviewed/README.zh-CN.md#project-37)。新稿以实际 Git 提交为依据，核对 checkpoint、pending writes、中断恢复及测试行为。

原稿中的代码行号和“恢复对账”推论不再作为独立证据。Agent 状态重建不自动保证外部 QPU/HPC 作业幂等；恢复必须查询平台事实，设备零自动重试和三句柄边界保持不变。

相关说明：[纠错记录](02-纠错记录.zh-CN.md)、[本地架构对照](03-本地架构对照与工程边界.zh-CN.md)、[工程衔接建议](04-工程衔接建议.zh-CN.md)。
