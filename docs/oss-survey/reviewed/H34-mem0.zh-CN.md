# H34 Mem0：身份字段、防元数据覆盖与缓存域

项目 `mem0ai/mem0`；SHA `2c81af3bbe27d9bccb09c772d583df9e9be72ee5`，提交2026-10-20T21:16:17-04:00；来源 `/tmp/oss-mem0ai-mem0`。静态阅读，不调用embedding/LLM/向量服务；许可根LICENSE。

## 实现链

Memory API把实体user_id/agent_id/run_id用于scope，再做提取、索引、搜索与history存储；main.py集中参数验证和元数据清理。上层认证必须决定这些ID，库的filter本身不是用户登录证明。

## 三个关键实现

- `_strip_identity_keys`拒绝由调用者metadata改变user/agent/run/actor域：创建时丢身份字段，更新时保留原scope；相同值可接受但不能改归属。
- `_validate_and_trim_entity_id`将非字符串转str并去首尾空白，拒绝空和内部空白。这是库兼容行为，公司合同若严格要求string不能照搬强制转换。
- 搜索参数检查top_k明确拒bool，但threshold只是number/range判定，不能据此声称所有NaN/Inf已完全处理；业务最终指标需现有finite检查。

```140:140:mem0/memory/main.py
_IDENTITY_KEYS = ENTITY_PARAMS | {"actor_id"}
```

## Scope测试

`tests/memory/test_session_scope.py:25-49`验证正常scope以及嵌入&user_id的ID不会与拆分filter碰撞；`:57-72`穷举分隔符组合检查唯一性。这是很实际的跨用户缓存反例，但不等于数据库ACL已完备。

## 遥测边界

main.py有敏感字段集合及后缀过滤，同时runtime auth对象允许保留以免破坏客户端配置；应仔细区分运行配置对象与要发给遥测的数据，不把深拷贝/字段过滤当全能脱敏。

## 公司落点

身份scope来自服务端托管账号而非模型metadata；知识检索前过滤、结果/导出再核验。`tests/`增加ID分隔符碰撞、更新metadata改租户、缓存跨用户、空query和不安全数值。
不默认自动写记忆为知识事实；来源、时效、撤回仍独立。LLM提取不替代platform算法catalog，原文/凭据不进上下文。

证据：main.py:94-140,143-171,174-239,255-269；test_session_scope.py:25-72；LICENSE。未审所有向量后端scope传播，不作“全链路租户安全”声明。
