# H51 llama.cpp：工具格式约束与执行授权分离

对象 `ggml-org/llama.cpp`；SHA `c7fc5094179bf8a9c73c18593db714f8da41a402`，提交2026-10-21T18:02:50-07:00；来源 `/tmp/oss-ggml-org-llama.cpp`。静态复核服务端OpenAI兼容参数及工具测试；未编译、未加载权重。根许可证以LICENSE为准。

## 实际链与参数约束

chat/completions请求 → `oaicompat_chat_params_parse` → tools/tool_choice与Jinja条件 → stop/response_format/schema/grammar转换 → messages检查 → 模板与推理。这里的兼容是参数及输出协议兼容，不是所有模型都具有同等工具能力，也不是已经与DSH端到端兼容。

```1357:1364:tools/server/server-common.cpp
    if (!opt.use_jinja) {
        if (has_tools) {
            throw std::runtime_error("tools param requires --jinja flag");
        }
        if (tool_choice != "auto") {
            throw std::runtime_error("tool_choice param requires --jinja flag");
        }
    }
```

非空json_schema与grammar同时出现被拒绝；response_format的json_object/json_schema转换成内部schema，空schema变为任意object。JSON语法或grammar约束只减少输出结构错误，不证明参数值有权限、资产属于当前租户或线路可以执行。

## 测试证据与限制

`tools/server/tests/unit/test_tool_call.py`定义普通/流式模式、工具schema及调用断言。`:99-125`辅助函数检查单个tool call、函数名和参数键，但它本身不是被pytest自动执行的测试；紧随其后的一批tiny模板测试被注释，不能算已运行覆盖。`:248-288`则是实际可收集的real-model测试：启动server并断言恰好一个调用、函数名及JSON参数键。它需要实际权重和启动预算，本轮未执行。

公司兼容测试应覆盖真实选用模型/模板的普通和流式tool_calls、混合content、空参数、非法JSON、取消、超时和上下文超限；只验证一个tiny模型不代表DeepSeek可用。模型供应链及权重许可也独立于llama.cpp自身许可。

## 公司取舍

适合CPU/边缘量化推理或特定部署优化；公司现有模型服务成熟时是备选基础设施，不是优先替换项。DSH保持唯一模型/工具循环；尤其本仓库还包含其他工具/MCP功能，不能因采用推理服务器而自动启用其执行面。

推理输出交回公司合同核验，坏信封拒绝、不做隐式修复；工具result仍遵守64000字节合同且科学全文留平台。无需把服务器内部会话ID变成额外业务句柄。

证据范围：`tools/server/server-common.cpp:1343-1364,1366-1390,1392-1408`；`tools/server/tests/unit/test_tool_call.py:46-62,99-125,127-148`；根LICENSE。现有测试辅助代码与注释项均明确区分，未给出模型质量结论。
