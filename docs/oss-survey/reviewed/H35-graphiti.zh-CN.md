# H35 Graphiti：图分区与时间过滤不是同一权限

对象 `getzep/graphiti`；SHA `8e320f880e7d169a907dbf2a7ac4188586c03b55`，提交2026-10-21T02:47:23+00:00；来源 `/tmp/oss-getzep-graphiti`。源码头Apache-2.0；静态阅读，未运行图数据库/LLM。

## 链路

Edge模型保存uuid/group_id/source/target/created_at；检索由SearchFilters组合时间、标签和关系约束，经各GraphProvider转换查询。分区group_ids必须在具体后端查询中传播，不能只在API参数里存在。

## 三个机制

1. SearchFilters分valid_at/invalid_at/created_at/expired_at，是四种不同时间条件，默认None不自动执行“过期隐藏”。旧稿把字段存在当默认时效保证，需收缩。
2. node_labels通过validator检查，query constructor还注明防model_construct绕过，这种双层校验适合公司合同注册与运行期一致检查。
3. Edge.delete对可选graph_operations_interface先尝试、NotImplementedError再走Provider具体查询；跨后端等价行为需要测试，不从共同接口自动推出。

```62:65:graphiti_core/search/search_filters.py
    valid_at: list[list[DateFilter]] | None = Field(default=None)
    invalid_at: list[list[DateFilter]] | None = Field(default=None)
    created_at: list[list[DateFilter]] | None = Field(default=None)
    expired_at: list[list[DateFilter]] | None = Field(default=None)
```

## 测试

`tests/test_neptune_search_isolation.py:60-86`对node/episode/community验证查询中group_id IN参数以及episode uuid关联；`:89-130`对新search operations再次验证。这些测试stub后端，证明查询构造而非整个平台认证。

## 公司映射

内部/外部知识先绑定server-side group/tenant，再构造时效过滤；派生摘要和导出必须继承权限。`knowledge.py`若换索引仍保留来源版本和不可信观测标识。
测试所有后端的group过滤、空组、过期/撤回数据、绕过model_construct与跨域节点关联。图谱时间不是设备账本，不能拿它恢复QPU提交。

证据：edges.py:1-15,49-87；search_filters.py:27-78,91-100；test_neptune_search_isolation.py:60-130。仅借模型/后端一致性方法，不要求部署完整图引擎。
