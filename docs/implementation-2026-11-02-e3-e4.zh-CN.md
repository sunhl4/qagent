# E3 / E4 执行记录（2026-11-02）

对应初始计划：`docs/company-agent-2000-person-days-development-plan-v1.0.json` 的 E3（P6-B）和 E4（P8-B）。本批次不引入第二个 Agent Runtime，不注册新的模型可见工具，也不把 DeepSeek SuperAgent 研究原型复制进生产 profile。

## E3：工作台状态轴与断线恢复

- `apps/company-workspace/host.mjs`
  - 工作台任务投影只接受合同内的 `dispatch` / `outcome` 记录和三类绑定操作。
  - 对事件进行严格状态排序：成功完成、明确拒绝、未知结果、派发中；非法组合被丢弃。
  - 同一 `request_id` 的重复事件不改变结果；旧时间戳不能覆盖新事实；成功结果没有合法 `business_ref` 时保持 `unknown`，不能伪造 `completed`。
  - 投影继续分离 `execution_state`、`result_state`、`approval_state`、`connection_state` 和 `billing_state`。P7 未完成时计费保持 `not_projected`。
  - 服务端按可信主体给 Python reconcile 子进程绑定 `COMPANY_AGENT_SUBJECT`，工作台任务只投影当前主体的回执。
  - 工作台缓存键由服务端解析的可信主体组成，不能由浏览器请求头直接指定；缓存清理按主体范围失效。
  - 导出 `restoreWorkbenchTasks()`：服务端查询暂时不可用时，只把已有快照标为 `reconnecting`，不把它升级为完成或取消。
- `apps/company-workspace/client.js`
  - 资源页在回执服务不可用或刷新异常时保留上次任务快照并显示重连状态；恢复后重新以服务端事实替换。
  - 只显示合法的服务端状态轴，不把右栏停止、前端事件或网络断开解释为平台取消。

## E4：租户撤权与越域反例

- `src/company_agent/receipts.py` 已按当前可信主体读取和 reconcile；本批次补充工作台宿主的主体绑定和缓存隔离。
- `src/company_agent/tenants.py` 继续每次读取 registry，撤权、过期、文件删除、坏 registry 和不可信主体立即失败闭合。
- `src/company_agent/knowledge.py` 继续按每个知识根目录独立读取 registry，撤权不影响其他知识根；知识命中仍是 `untrusted_reference_data`。
- `tests/test_governance_immediacy.py` 的回执 fixture 已与 receipts v1.2 字段合同一致，并覆盖跨主体读取隔离。
- `tests/ui/shell-host.test.mjs` 新增：乱序、重复、非法状态事件折叠；unknown 不被旧完成事件覆盖；无平台业务引用不显示完成；断线快照进入 `reconnecting`；可信主体解析和主体作用域缓存键隔离；主体无效时退回 `unknown@unknown`。

## 验证

- `node --check apps/company-workspace/host.mjs`：通过。
- `node --check apps/company-workspace/client.js`：通过。
- `node --test tests/ui/shell-host.test.mjs`：13/13 通过。
- `python -m pytest tests/test_governance_immediacy.py tests/test_receipts.py tests/test_tenants.py -q`：51 通过、1 跳过。

## 边界与未完成项

- 当前验证是本地 fixture、宿主路由和 Python 合同门禁；没有宣称真实企业 IdP、真实云/HPC/QPU、真实计费或跨客户端生产订阅验收完成。
- E5（模型/MCP）、E6（真实平台接缝）、E7（计费运营）继续等待 Owner 输入；E8（试点交接）不能因本批次本地通过而提前启动。
- 全量 Python 回归、真实 DSH sidecar/取消链和外部 Overleaf/插件环境仍需单独复验。
