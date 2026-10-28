# H37 LangGraph：checkpoint数据与外部副作用边界

对象 `langchain-ai/langgraph`；SHA `3cd57c038ad827d05f80c6488adea9994156c58c`，提交2026-10-21T21:22:40+09:00；来源 `/tmp/oss-langchain-ai-langgraph`。静态复核，不运行图或模型；许可根LICENSE/所用包。

## 实际链

Checkpoint记录channel_values、channel_versions、versions_seen；CheckpointTuple把config、metadata、parent_config与pending_writes关联。持久化saver按thread/ns/checkpoint定位快照；delta历史沿祖先收集写入后按统一排序重建状态。

## 关键机制

1. parent_config是祖先关系，不代表整个父快照全文复制；pending_writes是框架待归约写，不是平台“已受理未完成作业”。旧稿把两者近似为外部事务，必须纠正。
2. writes_sort_key返回task_path/task_id/idx；注释解释按task_id哈希排序可能打乱不可交换reducer，因此回放顺序必须和现场相同。
3. DeltaChannelHistory标Beta，字段可能变化；不应把该最新内部语义直接升级成公司的稳定合同。

```140:147:libs/checkpoint/langgraph/checkpoint/base/__init__.py
class CheckpointTuple(NamedTuple):
    """A tuple containing a checkpoint and its associated data."""

    config: RunnableConfig
    checkpoint: Checkpoint
    metadata: CheckpointMetadata
    parent_config: RunnableConfig | None = None
    pending_writes: list[PendingWrite] | None = None
```

## conformance测试

独立套件test_get_tuple.py:18-24检查不存在thread返回None；:27-50写三次后无checkpoint_id取最新，并检查metadata step；:53-71明确指定历史ID必须精确返回。说明存储接口可用统一行为套件测试多个后端，而不只测每个数据库实现。
本轮未执行该套件。

## 公司落点

借合同消费者一致性套件：各provider/plugin同样跑错信封、句柄、未知状态与短结果测试。恢复会话先查平台作业事实，设备零重试；checkpoint ID不是第四句柄，更不能变成twin_id。
`diagnostics.py`保留关联和unknown，后续持久化需明确写入顺序/父关联/幂等，但不引LangGraph第二Agent循环。

证据：base/__init__.py:94-120,140-147,150-182,185-196；conformance/spec/test_get_tuple.py:18-71；LICENSE。状态重建正确性不证明跨云/HPC/QPU exactly-once。
