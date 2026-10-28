# smolagents 调研更新入口

请阅读 [09 — smolagents 源码复核](reviewed/README.zh-CN.md#project-09)。执行器选择、工具/代码执行、导入检查与失败路径以固定源码和测试为准。

撤回“import 白名单可以直接作为安全沙箱”的表述。Python 限制解释器不等于操作系统强隔离；CodeAgent 循环也不能进入 DSH 生产路径。结果分析脚本同样需要受管执行、权限和输出合同。见 [沙箱汇总更新](C-汇总-沙箱与网络隔离.zh-CN.md)。
