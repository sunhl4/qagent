# H52 vLLM：服务端验证、模板信任与推理调度

对象 `vllm-project/vllm`；SHA `13058ef4d1fd7c6827de5ad70a669c6811c06ae9`，提交2026-10-22T12:45:27+08:00；来源 `/tmp/oss-vllm-project-vllm`。Apache-2.0（根LICENSE及源文件标识）。本轮静态检查chat入口及请求验证测试，未启动GPU服务。

## 实际链

ChatCompletionRequest验证 → 模型/LoRA及引擎前置检查 → OnlineRenderer → 构造请求关联信息 → 按engine_input计算token预算 → 转SamplingParams/BeamSearchParams → 引擎生成。不同输入子请求追加唯一后缀，用来区分推理请求，不能当作平台计算提交的幂等机制。

```278:285:vllm/entrypoints/openai/chat_completion/serving.py
        error_check_ret = await self._check_model(request)
        if error_check_ret is not None:
            logger.error("Error with model %s", error_check_ret)
            return error_check_ret

        self._preflight(request.n or 1)

        return await self.online_renderer.render_chat(request)
```

构造参数中`trust_request_chat_template`与自动tools开关默认false；“是否采用请求提供模板”应作为服务信任配置，而不是任意用户自由改系统模板。token预算结合模型长度、prompt长度和max_completion_tokens等参数，不是简单透传客户端数字。`_log_inputs`存在日志调用，真实部署须核对日志配置与脱敏，不能宣称本地部署自然无数据留存。

## 测试证据

`tests/tool_use/test_chat_completion_request_validations.py:10-64`断言未传tools/None时tool_choice为none，空tools数组拒绝，auto/required却无tools拒绝。`:67-105`处理reasoning_content兼容字段。这是模型API输入层规范化，与公司业务信封禁止未知字段属于不同层，不能直接把兼容别名放入业务合同。

本轮未执行上游测试，也没有验证公司DeepSeek权重、量化、tool parser或GPU吞吐。是否兼容取决于实际模型、chat模板、解析器及部署版本。

## 公司落点

若现有本地推理平台已用vLLM，优先增加DSH消费者合同测试和运维指标，而非重新搭一套。模型层负责推理队列/批处理，成熟HPC/QPU平台负责计算作业调度；两种调度不能因都叫scheduler就混成同一模块。

工具调用输出只交给DSH及公司严格入口；云/HPC凭据和设备权限不下放模型服务器。模型请求ID用于追踪，账号、租户、预算与审批由宿主注入并再次验证。观察推理token成本可以辅助计量，但不代替平台计算计费。

证据范围：`vllm/entrypoints/openai/chat_completion/serving.py:125-145,264-284,307-343,345-385`；`tests/tool_use/test_chat_completion_request_validations.py:10-64`；根LICENSE。未评估完整分布式安全和GPU隔离。
