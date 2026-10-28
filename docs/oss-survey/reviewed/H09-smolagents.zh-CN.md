# H09 smolagents：代码工具与执行器边界

项目 `huggingface/smolagents`；SHA `96f33faaf028479119ec8d34507b47694cf14e34`，提交2026-10-06T11:38:53+02:00；来源 `/tmp/oss-huggingface-smolagents`。根LICENSE及源码头Apache-2.0。静态复核，未运行科学包/模型。

## 链路

CodeAgent把模型工具动作表示成代码，构造时选择prompt模板、authorized imports、stream模式和执行器；create_python_executor根据local/blaxel/e2b/modal/docker生成对应对象，结果回到自己的MultiStepAgent循环。

## 三个机制

- additional_authorized_imports与BASE_BUILTIN_MODULES合并去重；`*`仅产生告警并允许宽泛导入，不能称为不可绕过的强隔离。
- stream_outputs=True但模型没有generate_stream会提前报错；不支持的executor_type也报错；managed agents与remote code execution组合明确不支持。
- cleanup经context manager退出调用执行器清理，但本地解释器限制不等于操作系统沙箱，真实进程/文件/网络边界需另验。

```1593:1596:src/smolagents/agents.py
    def cleanup(self):
        """Clean up resources used by the agent, such as the remote Python executor."""
        if hasattr(self.python_executor, "cleanup"):
            self.python_executor.cleanup()
```

## 测试

`tests/test_local_python_executor.py:58-75`检查赋值与状态；`:77-81`禁止覆盖已登记tool；`:91-100`只允许注册函数调用，缺少工具时抛InterpreterError。
这些断言有价值，但不是恶意代码不能逃逸的完整证明。本轮未运行测试。

## 公司取舍

不引CodeAgent循环，不直接import科学算法包。中栏结果分析若需要执行脚本，应通过受管平台执行器，参数和输出仍经公司合同。
`tests/`可补越界import、覆写tool、执行器清理失败、输出超限与凭据访问等反例。
设备调用不能藏在生成代码中绕过quantum_device_run；既有三句柄不扩展为executor ID。

证据：agents.py:1505-1545,1556-1585,1593-1615；test_local_python_executor.py:1-14,58-100。版本注释Added1.17.0是功能加入时间，不是仓库当前版本，旧稿误用撤回。
