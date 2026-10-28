# H25 非官方 Qiskit MCP：全局线路状态与输出风险复核

- 对象：`barvhaim/qiskit-mcp-server`。
- SHA：`9f39d6269ed6bdfb314c4f5c35782b896c80f4f1`，2025-07-30T22:43:51+03:00。
- 来源：`/tmp/oss-barvhaim-qiskit-mcp-server`。
- 验证：静态阅读；未 import Qiskit、未运行线路、未提交作业。

## 范围和许可纠错

追踪文件树只有 main.py、pyproject、README、examples 等，未看到 LICENSE。pyproject:1-15 也没有 license 声明。旧速评的 MIT 无原文依据，撤回；没有许可授权不能默认可复制分发。
本次未发现测试套件，examples 不能算自动化回归。明确留下验证缺口，不伪造测试证据。

## 调用链

FastMCP 装饰器直接注册 create_quantum_circuit、add_gates、run_circuit 等函数。
线路对象保存在进程全局 circuits 字典，通过字符串 name 取得。
run_circuit 查询字典，创建 BasicProvider，transpile 后同步执行 job.result，再把 counts 序列化为 JSON 字符串。
证据：`main.py:1-24,26-60,113-147`。

## 机制一：名称唯一不等于授权资源身份

创建时给默认 name 加毫秒时间与UUID片段，用户指定重名时加后缀。
这只避免同一字典键冲突，没有 tenant/user 命名域或访问控制证据。
进程重启也会丢失 circuits；不能当可持久化业务资产。
公司必须使用平台 asset_id/circuit_id，不把任意 circuit_name 当授权依据。

## 机制二：增量修改可能部分成功

`add_gates` 循环逐个修改线路，遇不支持 gate_type 直接返回错误字符串。
前面已加的门没有回滚，因此错误不代表“未改变线路”。
对公司重要的是错误状态与副作用状态分离，不是复制这个可变全局字典实现。
证据：`main.py:63-110`。

## 机制三：全量测量结果直接返给模型

run_circuit 返回 results: counts 和总次数，未见该路径的集合/字节预算。
全量 bitstring counts 与公司短结果硬规则冲突；公司只允许受管统计摘要和平台资产引用。
该项目直接导入科学包，也不符合公司 Agent 不 import 算法包的边界。

```14:18:main.py
# Global circuit storage
circuits: Dict[str, QuantumCircuit] = {}

# Initialize MCP server
mcp = FastMCP("Qiskit MCP Server")
```

## 公司映射

1. 量子 MCP 只能通过现有平台 provider 组织任务，算法由 catalog 发现，不复制这里的科学执行函数。
2. `contracts/tools.json` 保持输入/输出句柄所有权；线路名不成为第四句柄。
3. `sanitize.py` 的禁止字段和限额测试覆盖 counts/完整线路/敏感科学数据。
4. 任务回执需区分部分修改、未执行、已执行和未知，不能把普通错误字符串当完整状态。
5. 多租户请求必须在资源查询之前鉴权，全局字典不能当企业隔离实现。

## 结论与缺口

这是有用的反例样本：MCP 封装让工具可调用，但没有自动获得多租户、持久化、短结果和审批治理。
不采用为生产量子接入组件。许可证未明确、测试缺失、真实执行未验证均须保留，不能为了计数标“已集成”。

## 证据

`main.py:1-24,26-60,63-110,113-147`；`pyproject.toml:1-15`；仓库固定版本追踪树用于核对测试/许可缺口。
