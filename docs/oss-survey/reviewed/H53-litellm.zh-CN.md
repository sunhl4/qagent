# H53 LiteLLM：预算计数命名与读写一致性

对象 `berriai/litellm`；SHA `f2118fc7670ba3fa736d9b8f4deef9077a45a720`，提交2026-10-22T02:09:52+00:00；来源 `/tmp/oss-berriai-litellm`。根LICENSE：enterprise目录另有许可，其余MIT。静态复核模型预算hook与对应单测；未部署代理或迁移公司模型入口。

## 实际预算链

解析请求模型对应预算配置 → 统一生成entity/model/window计数键 → 预调用预算检查 → 成功后增量记账 → 使用量接口读取同一计数。`ResolvedModelBudget`保留的是运维配置的budget_model，而不是请求随意使用的模型别名；读写必须绑定同一个规范名称，否则别名可能分裂额度。

```75:82:litellm/proxy/hooks/model_max_budget_limiter.py
def model_budget_spend_cache_key(
    entity_type: Litellm_EntityType,
    entity_id: str | None,
    budget_model: str,
    budget_duration: str | None,
) -> str:
    """Sole owner of the per-model spend counter key, shared by its writer and all of its readers."""
    return f"{_SPEND_CACHE_KEY_PREFIXES[entity_type]}:{entity_id}:{budget_model}:{budget_duration}"
```

实体范围包括key、user、end_user、team、team_member；team_member用用户ID长度前缀避免含冒号的ID组合碰撞。窗口起始键也按预算模型区分，防止短周期重置长周期。升级兼容读取旧请求模型名称的计数，在进程启动一个预算窗口后停止。

无效预算配置在该读路径会警告并继续寻找候选项，写路径另有验证；这种可用性取舍不能直接当作公司“未知配置必拒绝”的执行政策。预检查与事后增量也不能仅凭这两步推断全局并发额度绝不超额，需要另审共享缓存、原子预留及故障恢复。

## 测试与公司落点

`tests/unit/proxy/hooks/test_model_max_budget_limiter.py:111-191`覆盖成功后扣费并拒绝超额、组合ID不碰撞、不同用户/团队隔离及零预算首请求拒绝。它提供可直接借鉴的边界测试；本轮未执行，未验证分布式部署。

公司可统一预算主体与计数键设计，但模型token预算与成熟云/HPC/QPU平台计算账单必须分账。任务预估、额度预留、平台实际费用及退款调整需要可追溯状态，不应把模型hook当完整财务账本。

已有模型网关够用时不新增LiteLLM依赖；若引入，只作推理接入基础设施，DSH继续唯一Runtime。企业功能的许可、模型路由出口、headers、日志和密钥隔离需单独验收，不把共享服务key暴露客户端或模型。

证据范围：`litellm/proxy/hooks/model_max_budget_limiter.py:24-54,57-81,84-115,118-154`；上述测试`:111-191`；`LICENSE:1-26`。本轮不构成财务正确性或代理整体安全认证。
