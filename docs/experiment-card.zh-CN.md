# 实验卡

启动一次研究迭代前填写本表。填完的值交给 `company_research_compile` 校验，通过后再交给 `company_research_run`。两次调用使用同一行的值。`company_research_run` 另加本次的 `idempotency_key`。

这张表只驱动 `company-agent-research`。`hpc` 只交接给 `hpc_submit`，回执字段是 `job_name,script`。`cloud` 只交接给 `quantum_cloud_submit`，回执字段是 `program_path,target,shots`。`qpu` 只做真机批准交接，回执字段是 `circuit_id,shots`。这三步都不在研究运行里提交。下一次提交仍要单独批准。

`baseline_reproduced` 为 `false`，或没有 `baseline_metric` 时，编译直接拒绝，运行不开始。当前时钟的指标读数是 `val_loss`，所以 `primary_metric` 填 `val_loss`。`changed_path` 指向研究根目录里的指标日志。一行是一次尝试：`val_loss=<数字>`，可加 `train_time_seconds=<数字>`。同一 `attempt=` 的多行是一次尝试的多个种子。`baseline_train_time_seconds` 可空；填了之后，训练时间均值比它高出一成以上就撤销这次尝试。`min_seeds` 可空，默认 1，最大 3。种子不够，或相对标准差超过 0.5，这次运行停止，下一张卡要换 `changed_path`。Git 仓库里，每次尝试只把当前候选写进该次 worktree 的同一路径并做一次本地提交，主目录里的候选文件保持原样。`max_attempts` 为 1 到 5。一次批准内部按这个次数修改再跑，出现保留或预算用尽即停止。章程是问题、基线、指标和预算。第一次成功运行记下新立；以后只在回执里写下变了的槽位名，不写槽位正文。下一轮填写新卡，或由用户明确要求再跑一次。

同一张表可以做成 WPS 表格。研究插件读取的是下面这些单元格的值，不打开 xlsx。

| 字段 | 填写 |
| --- | --- |
| tenant_id |  |
| experiment_id |  |
| task_id |  |
| hypothesis |  |
| falsifier |  |
| baseline_name |  |
| baseline_source |  |
| baseline_metric |  |
| baseline_reproduced |  |
| baseline_train_time_seconds | 可空 |
| min_seeds | 可空，1 到 3 |
| changed_path |  |
| primary_metric | val_loss |
| direction | minimize |
| resource_type | cpu |
| max_cost |  |
| max_attempts |  |
