# H24 Qiskit MCP servers：账户服务与异步作业接口边界

项目 `Qiskit/mcp-servers`；SHA `b763581b5a2958a172092c02cc6ac32bcbd46be9`，提交2026-10-08T14:16:45+02:00；来源 `/tmp/oss-Qiskit-mcp-servers`。阅读IBM Runtime模块；文件头Apache-2.0。未import科学包、运行测试或访问IBM。

## 链路

server.py注册FastMCP工具，包装ibm_runtime函数。账户工具可接token或使用环境/已保存凭据；后续查询backend、提交、状态轮询与结果回收分开。核心ibm_runtime模块直接使用Qiskit SDK，存在进程全局service和十线程backend查询池。

## 三个机制与公司差异

1. setup工具把token作为可见参数，适合通用开发工具但不符合公司密钥托管/模型不可见目标；公司只允许服务端授权注入。
2. least_busy过滤operational backend、忽略状态查询异常、按pending_jobs排序。这只是候选选择，不能保证资源配额或异构QPU/HPC最优调度。
3. 服务全局实例是进程级状态，不直接证明多用户隔离；内部/外部账号不能共用此状态而无主体绑定。

```100:104:qiskit-ibm-runtime-mcp-server/src/qiskit_ibm_runtime_mcp_server/ibm_runtime.py
# Global service instance
service: QiskitRuntimeService | None = None

# Thread pool for parallel backend operations (limit concurrent API calls)
_backend_executor = ThreadPoolExecutor(max_workers=10)
```

## 测试

`qiskit-ibm-runtime-mcp-server/tests/test_server.py:58-83`验证有效token、缺失、placeholder、空白值。它不测试公司账号、真机批准或资源计费；未运行。

## 公司落点

作业受理/完成分开值得借；具体实现仍从平台provider调用，Agent不直接import Qiskit。
算法目录只用algorithm.catalog，不把示例线路/算法名写入公司生产目录。完整counts/Pauli/校准正文不得回模型。
job_id是外部关联信息，不能扩展三句柄或将普通作业签为twin_id。
测试加入凭据缺失、异步未完成、结果不可用、错租户job、backend查询失败与状态过期。

证据：server.py:71-115；ibm_runtime.py:39-54,57-80,83-104；test_server.py:1-11,58-83。未审全部qiskit/gym/docs/transpiler子服务，不能以一套FastMCP证明公司量子治理已满足。
