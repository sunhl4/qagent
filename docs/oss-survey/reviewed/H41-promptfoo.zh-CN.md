# H41 Promptfoo：离线攻击评测与生产严格信封分离

对象 `promptfoo/promptfoo`；SHA `03844fb957487102bd21f7434a229915cee90e02`，提交2026-10-22T09:49:52+08:00；来源 `/tmp/oss-promptfoo-promptfoo`。本轮静态检查MCP调用规范化及其评测测试，未连接公司的模型或执行攻击。许可按根LICENSE及具体附加组件审查。

## 实现链

评测输入 → `parseMcpToolCall` → 允许工具名集合 → 参数别名选择 → Ajv按工具schema验证 → 统一输出。字符串先尝试JSON解析；数组、null和非对象拒绝。工具名只从允许集匹配，未知工具不会被直接接受。

关键区别是该评测工具刻意兼容多种模型输出：工具名可为`tool/toolName/function/functionName/name`，参数可为`args/arguments/params/parameters`。参数缺失或不是对象时回退为空对象；工具无schema时只要求object。Ajv设置`strictSchema:false`是schema编译策略，不等价于公司合同必须拒绝未知信封字段。

```48:57:src/redteam/mcpToolCall.ts
  const rawArgs =
    TOOL_ARGS_FIELDS.map((field) => record[field]).find(
      (fieldValue) =>
        typeof fieldValue === 'object' && fieldValue !== null && !Array.isArray(fieldValue),
    ) ?? {};

  return {
    tool: toolName,
    args: rawArgs as Record<string, unknown>,
  };
```

## 测试证据与边界

`test/redteam/mcpMaterialization.test.ts:35-79`明确断言合法调用不触发模型、别名被规范化、非法数组参数在无参工具上回退为空对象。这是设计意图的直接证据，而不是我们推测的潜在行为。后续测试模拟模型将自然语言转成调用，但本轮未执行这些测试。

## 公司适配

可以复用评测方法，不复用宽容生产解析：构造未知工具、参数类型错误、伪造身份、跨租户资产、恶意网页、工具输出注入及审批绕过样例；用本地模型的测试端点和无副作用provider运行。失败判据由`contracts/`与平台事实定义，不由被测模型自评。

生产`company-agent invoke`继续只接受严格合同字段，缺失provider、未知preset和坏信封失败闭合。评测适配器中的别名修复不能进入公司南向执行链。设备测试只能使用替身，不能因“红队任务”绕过lab/sign审批或触发boot/algo执行。

证据范围：`src/redteam/mcpToolCall.ts:14-32,34-57,60-88`；`test/redteam/mcpMaterialization.test.ts:35-79`；根LICENSE。此文不评价完整攻击集的覆盖率，也不把评测通过当作商业安全认证。
