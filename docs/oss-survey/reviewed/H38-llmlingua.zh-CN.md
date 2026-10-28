# H38 LLMLingua：只压缩可损失的检索上下文

对象 `microsoft/LLMLingua`；SHA `5a4c78ae18ab17a98cf997e8259354e546081d64`，提交2026-09-10T16:36:23-07:00；来源 `/tmp/oss-microsoft-LLMLingua`。MIT（根LICENSE）。本轮静态源码复核，未下载权重、执行推理或测量公司的DeepSeek质量。

## 实际调用链与代码机制

`PromptCompressor`初始化分词器与模型 → `compress_prompt`或结构化入口 → 按上下文、句子、token筛选 → 返回压缩文本及token计数。`load_model`按模型architecture选择token分类或因果语言模型；`get_ppl`用移位logits/labels计算交叉熵，支持按句或token粒度返回。压缩器本身也是一项模型推理开销，并不是无成本字符串截断。

`compress_json`先把结构化JSON变为上下文和强制保留索引，再调用结构化压缩，清理连续逗号后重新`json.loads`。能被JSON解析只证明语法有效，不证明参数、量子物理含义、引用关系完整。结构化入口支持不压缩片段，但保留策略仍须由调用者定义。

```121:126:llmlingua/prompt_compressor.py
        trust_remote_code = model_config.get("trust_remote_code", True)
        if "trust_remote_code" not in model_config:
            model_config["trust_remote_code"] = trust_remote_code
        config = AutoConfig.from_pretrained(model_name, **model_config)
        tokenizer = AutoTokenizer.from_pretrained(model_name, **model_config)
        if model_config.get("pad_to_left", True):
```

默认允许模型仓库自定义代码，是独立供应链边界；公司若试验应固定权重版本、离线制品和允许清单，不能把任意用户模型名交给此加载器。

## 测试证据及其边界

`tests/test_llmlingua2.py:43-80`以CPU加载指定模型，断言压缩文本、原始98 tokens、压缩后30/34 tokens及比例。它验证固定样本的可重复输出，不验证中文内部算法文档、QASM、审批条款或任务提交字段的语义保持；本轮未运行，需要权重依赖。

## 公司适配与取舍

适合作为知识检索之后、进入DSH上下文之前的可选离线评估项。原始文档仍保存于受访问控制的知识服务，压缩摘要保留来源及版本，可回看原文。先用公司问答集验证答案与引用，再决定是否启用；已有本地DeepSeek无需替换。

合同、权限、设备审批、`component_id`、句柄、QASM正文及提交信封不做有损压缩。输出预算继续遵守`contracts/results.json`，压缩器不充当短结果或敏感数据过滤器。禁止让模型压缩后的文本成为授权依据。

证据范围：`llmlingua/prompt_compressor.py:118-165`加载模型，`:167-216`困惑度计算，`:221-280`JSON重建，`:282-320`结构化选项；`tests/test_llmlingua2.py:43-80`；`LICENSE:1-21`。结论仅覆盖上述压缩路径。
