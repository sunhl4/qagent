# H44 Simple-evals：可读的小型评测合同与报告

对象 `openai/simple-evals`；SHA `652c89d0ca9df547706735883097e9537d40dc47`，提交2026-04-22T15:16:16-07:00；来源 `/tmp/oss-openai-simple-evals`。本轮静态复核类型、聚合、HTML展示与评分单测；未调用模型、未跑基准。许可以根LICENSE为准。

## 实际链及机制

Sampler接收消息列表并返回回答、实际查询消息与元数据 → 单样本评测产生score/metrics/对话/说明 → `aggregate_results`逐指标计算统计量 → HTML报告展示。`SamplerBase`/`Eval`是极小接口，便于用公司已有本地模型写测试适配器；不意味着必须采用OpenAI服务。

```9:16:types.py
@dataclass
class SamplerResponse:
    """
    Response from a sampler.
    """
    response_text: str
    actual_queried_message_list: MessageList
    response_metadata: dict[str, Any]
```

聚合器对score为None的项不累计score，但保留各样本元数据；不同metric可能覆盖不同数量样本。报告只给均值而不说明有效样本数时，容易产生可比性误解，公司应额外记录缺失、超时与拒绝的分母。

`map_with_progress`使用ThreadPool且线程数取输入长度上限；这是批处理并发，不是生产任务调度。空输入在非debug路径可能得到0线程，需单独测试和防护，不能据静态判断宣称已复现异常。HTML环境启用自动转义，消息走模板；评测生成的HTML片段仍需明确可信来源，不能据一处autoescape断言整站无注入风险。

## 测试与公司落点

`healthbench_eval_test.py:8-38`验证负分rubric扣分、分母只累计正分项及长度惩罚。它说明权重与分母应有可执行断言，不能直接迁移医学评价标准到量子任务。本轮未执行。

建议用小型公司评测合同记录：输入自然语言/允许能力、预期审批、平台替身行为、结构化结果、终态和可追溯制品。数值结果格式与绘图模板另有确定性检查；模型解释质量与科学正确性分开计分。对话和实际发送消息可能含敏感上下文，评测报告必须脱敏并受租户访问控制。

该项目可作为测试设计参考，不承担企业身份、预算授权、HPC/QPU状态对账，也不替代DSH。没有在本轮配置模型或认证信息。

证据范围：`types.py:9-27,31-56,59-66`；`common.py:195-217,220-235,238-265`；`healthbench_eval_test.py:8-38`；根LICENSE。评分器通过不等于科学计算正确。
