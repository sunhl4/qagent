# container-use 调研更新入口

请阅读 [31 — container-use 源码复核](reviewed/README.zh-CN.md#project-31)。工作区、容器和版本控制的实际调用链以新稿证据为准。

工作区分支或容器检查点不是外部作业事务，也不拥有 `twin_id`。已提交的 QPU/HPC 作业必须向业务平台查询和对账，不能靠 checkout 回滚。见 [本地架构对照](03-本地架构对照与工程边界.zh-CN.md)。
