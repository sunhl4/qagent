# H07 Aider：代码仓上下文检索复核

- 研究对象：`Aider-AI/aider`，不把最近提交时间解释为停止维护。
- 固定 SHA：`5dc9490bb35f9729ef2c95d00a19ccd30c26339c`。
- 提交时间：2026-05-22T07:02:20-07:00。
- 本地来源：`/tmp/oss-Aider-AI-aider`。
- 许可证：根 `LICENSE.txt:2-24` 为 Apache-2.0；具体依赖许可需另查。
- 验证级别：静态源码与测试阅读，未调用模型、未运行上游测试。

## 定位与边界

Aider 是完整编码助手，本次重点读其 repo map，而不是引入其 Agent 循环。
它将代码仓转换为优先级排序后的符号上下文，适合内部软件接口检索的机制参考。
与简单把全部文件拼接进提示词不同，预算与关联性贯穿选择过程。
公司可借上下文选择思想，但 DSH 仍是唯一对话运行时。

## 实际调用链

`RepoMap.get_repo_map()` 接收聊天内文件、其他文件、被提及文件和标识符。
它先检查 map token 开关和候选文件集合，再选择本次预算。
没有聊天内文件时，允许按 `map_mul_no_files` 扩大概览，同时保留上下文余量。
随后进入 `get_ranked_tags_map()`，再由 `get_ranked_tags()` 收集定义和引用。
`get_tags()` 使用文件 mtime 和磁盘缓存，解析出的 Tag 带文件、行、名称和类型。
排名结果重新按源码上下文渲染并放入仓库概览，而不是把排名当权限。
入口证据：`aider/repomap.py:103-167`；缓存入口：`:225-240`。

## 机制一：token 计数是估计值，不是硬字节限制

`token_count()` 对短文本直接调用模型 tokenizer，对长文本抽取行样本再外推。
这降低重复渲染/计数成本，但估计可能偏离实际 tokenizer。
因此它适合检索预算优化，不适合公司最终工具结果字节上限。
公司 `contracts/results.json` 和 `validate_result_size()` 仍应做最后的确定性约束。
证据：`aider/repomap.py:89-101`。

## 机制二：关联图排序而非任意全量读取

`get_ranked_tags()` 先对文件排序，建立 definitions、references 与 personalization。
聊天内文件、显式提及文件、路径中提及标识符影响个性化权重。
对同名定义过多和下划线私有符号降低权重，对显式提及和可辨识名称提高权重。
引用边采用平方根计数，避免高频低信息符号完全支配排序。
多重有向图随后用 PageRank 排序，再将节点贡献分配给定义。
证据：`aider/repomap.py:365-520`。

这对公司内部算法接口文档有启发：检索可优先返回相关接口摘要，而非代码正文。
但候选文件必须先经过用户/租户授权；排名从不构成读权限。
算法可执行目录仍从平台 `algorithm.catalog` 获得，repo map 不能替代目录。

## 机制三：缓存失败有降级，解析递归失败有关闭

缓存 SQLite 操作出错时，代码尝试重建缓存，仍失败则回退进程内字典。
这是性能缓存的可接受降级，与“权限数据库失效仍放行”不是同一类行为。
`get_repo_map()` 遇到 `RecursionError` 会发出错误提示并将 map token 上限置零。
这意味着检索上下文缺失需可见，不能告诉用户“已完整读过仓库”。
证据：`aider/repomap.py:143-147,177-221`。

```143:147:aider/repomap.py
        except RecursionError:
            self.io.tool_error("Disabling repo map, git repo too large?")
            self.max_map_tokens = 0
            return

```

## 测试证据

`tests/basic/test_repomap.py:21-44` 创建 Python/Markdown/JSON 空文件，断言概览包含各文件。
它证明基本候选文件呈现，不证明权限隔离、敏感数据过滤或排名业务准确性。
`:49-100` 的 refresh=files 测试先追加函数，然后确认文件集合不变时概览未刷新。
改变文件集合后，新函数出现，说明缓存刷新策略会影响内容新鲜度。
这对知识库场景尤其重要：缓存命中不能被理解为源内容未变。
本次未运行这些测试，结果只作为已有断言分析。

## 公司映射与回归建议

1. 在内部知识/源码检索 provider 侧采用符号摘要与排名，DSH 插件仍只转调。
2. `contracts/tools.json` 应定义有来源版本的短摘要，不返回完整算法实现。
3. `tests/test_knowledge.py` 方向增加“源更新但缓存未刷新”的可见状态或失效验证。
4. `tests/test_sanitize.py` 继续负责最终结果预算，不能以估计 token 替代字节限制。
5. 代码仓访问权限必须在枚举和解析前过滤，摘要与导出时再次核对。

## 不采用的部分

不引入 Aider 模型/工具循环、自动 Git 修改和 shell 执行作为生产路径。
本项目的内部用户可以有额外资料权限，外部用户不能靠同一 repo map 越域检索。
也不能依据“Apache 许可”推断内部源代码可以任意对外发送。

## 深度复核结论

最有价值的是候选压缩、符号图排序与缓存新鲜度边界。
最需纠正的是旧稿把提交较早直接标“停推”，以及把上下文压缩误当硬结果预算。
采用之前应验证中文接口描述、权限过滤、增量更新和真实模型 token 偏差。
这些验收尚未执行，不在静态复核完成口径内。

## 证据锚

- `LICENSE.txt:2-24`：许可。
- `aider/repomap.py:89-101`：token 估算。
- `aider/repomap.py:103-167`：入口/预算/失败。
- `aider/repomap.py:177-221`：缓存错误降级。
- `aider/repomap.py:365-520`：符号图与排名。
- `tests/basic/test_repomap.py:21-44`：基本呈现断言。
- `tests/basic/test_repomap.py:49-100`：刷新行为断言。
