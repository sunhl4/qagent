# 公司执行面翻译层

这个目录是研究层 `ComputePort` 的一个实现。它把 `cpu`、`gpu`、`hpc`、`cloud`、`browser` 翻译成 `company-agent-provider/1.0` 信封，并保留原来的资源种类。

它不 import 根目录的云、HPC 或模型实现，也不发起网络调用。`degraded` 保持为真。研究层默认仍装配 `adapters/stub/`。进程内去重只属于当前适配器实例，不是公司事实源。

`qpu` 不提交作业。它只生成设备审批交接，字段是租户、请求标识、幂等键、`mandate=lab` 和工具名 `quantum_device_run`。公司控制面把这条交接记成候选触发，不开工单，也不调用设备。

未知、超时、未决、排队和运行中的状态都可以查询，都不能重新提交。报价、日志和模型正文在 `degraded: true` 时保持 blocked。本阶段只把 `HP-02`、`HP-05`、`CL-01` 记为通过。
