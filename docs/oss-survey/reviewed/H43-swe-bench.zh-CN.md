# H43 SWE-bench：避免把未运行与跳过测试判成成功

对象 `SWE-bench/SWE-bench`；SHA `02e7a74ffd0b707aab73d203fe87bdc7c76afc8e`，提交2026-09-02T01:50:34+00:00；来源 `/tmp/oss-SWE-bench-SWE-bench`。本轮静态复核评分器及跳过测试回归，未运行容器基准；许可以根LICENSE为准。

## 评分链与关键细节

日志文件 → 应用补丁/环境错误标记检查 → 测试输出起止标记 → 仓库特定解析器 → 非空结果或实际执行证据 → 测试命令退出码交叉检查 → 修复/保持分类 → 汇总。单看模型回答“已完成”或日志中出现PASSED不构成成功证据。

`SUITE_RAN`要求正数执行计数，专门排除“Executed 0 of 0”。空结果先尝试完整日志解析；仍为空且无执行证据才判无效，兼顾某些仅输出失败项的测试器。非零退出码却没有失败状态同样判无效。

```155:160:swebench/harness/grading.py
        if not status_map and not SUITE_RAN.search(content):
            # No parsed results *and* no sign the suite ran: the run is invalid, not
            # a pass. Under EvalType.FAIL_ONLY an absent test counts as success, so
            # without this a suite that never started (e.g. a browser that fails to
            # launch) scores every F2P test as resolved.
            return {}, False
```

失败转通过（F2P）与保持通过（P2P）的跳过语义不同：跳过修复目标不算修复，跳过原有通过项在此基准中不算回归。这是特定评分政策，公司的计费、科学正确性验收不能直接套用。截断参数化测试ID的前缀匹配也是数据集兼容处理，源码自身标注应迁出通用评分器。

## 测试证据与公司适配

`tests/test_grading_skipped.py:35-60`断言全部修复项被skip时不应算resolved、原通过项被skip不阻止该基准的full。这个回归适合转化为公司的“零执行、空结果、全部跳过、状态矛盾均不能宣称作业成功”测试。本轮未执行上游测试。

公司成功必须来自云/HPC/QPU平台的作业事实、结果制品与格式/科学检查，而不是DSH叙述。未知状态独立于失败、取消和成功；提交超时先对账，不自动重投设备。评估可借鉴运行元数据、解析器和断言分层，但不引入新的生产Agent循环，也不把SWE编码分数解释为量子任务可靠率。

证据范围：`swebench/harness/grading.py:24-58,60-112,130-176`；`tests/test_grading_skipped.py:35-60`；根LICENSE。日志交叉检查提高可信度，但单靠可由任务代码写出的日志不等于防篡改证明。
