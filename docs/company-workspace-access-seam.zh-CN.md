# 公司工作台接入接缝（access seam）· 对外契约 v1

状态：草签（2026-10-22）。本页定义公司工作台「账号/开通/凭据」链路的**可替换接缝**：UI 与 Agent 只依赖本文列出的 HTTP 面与数据形状，服务端实现可以先由演示壳内建（现状），之后按同一契约切换到公司已有的内部客户端 / 身份与授权服务，UI 与对话层不需要改。

## 1. 谁依赖这个契约

| 依赖方 | 依赖内容 | 不依赖 |
| --- | --- | --- |
| `apps/company-workspace/client.js`（原生设置对话框的平台连接页 + 通用行） | §2 的 HTTP 面与 JSON 形状 | 服务端实现方式（本机文件 × 内部客户端） |
| 管理员审批入口 | §2 的 grant 面与 `x-admin-token` 语义 | demo 的本地文件存储 |
| DSH 原生界面 / 模型对话 | 只见布尔连接状态，不见凭据与审批细节 | 凭据明文（任何人都不可见,唯一例外是服务端进程注入目标服务） |
| 公司内部客户端（未来实现者） | 本契约 + §4 替换清单 | 演示壳内部实现 |

## 2. 客户端可见 HTTP 面（稳定面，改动需走合同流程）

宿主仅绑定回环 `127.0.0.1`；默认端口为 `3081`，可通过启动变量 `COMPANY_AGENT_DSH_PORT` 指定一个 1–65535 的整数端口。可信 Host 必须精确等于本次配置的 `127.0.0.1:<port>`，Origin（若存在）必须精确等于 `http://127.0.0.1:<port>`；不接受其他端口或从请求头推导信任域。全部要求浏览器认证（与索引页同一 cookie 席位，grant 例外见下文）且 `Sec-Fetch-Site` 非 cross-site；所有响应 `cache-control: no-store`、无凭据字段。

| 方法+路径 | 输入 | 成功响应（形状即契约） |
| --- | --- | --- |
| `GET /company-workspace/access` | 浏览器会话 | `{"cloud":{"open":bool},"hpc":{"open":bool},"requests":[{"id","kind","account","requestedAt","status"}]}`；`requests` 为最近 ≤20 条、新在前；`status ∈ pending\|granted` |
| `POST /company-workspace/access` | `{"kind":"cloud"\|"hpc","account"?:str≤80}` | `{ok:true,pending:true}`；未知 `kind` → 400 + `{"error":"kind 必须是 cloud 或 hpc"}` |
| `POST /company-workspace/access/grant` | `{"kind","account"?,"cloudKey"?}` + 头 `x-admin-token` | `{ok:true,"granted":{"kind":"...","open":bool,"requestsUpdated":n}}`；管理员批准并把凭据写入服务端配置（0600），随后刷新连接状态缓存 |
| `GET /company-workspace/{cloud,hpc}/status` | 浏览器会话 | `{"connected":bool,"reason"?}`；`reason ∈ connected\|missing_api_key\|auth_failed\|unconfigured\|fetch_failed` |
| `GET /company-workspace/{cloud,hpc}/overview` | 浏览器会话 | 服务概览（设备清单/作业），只读投影 |
| `GET|POST /company-workspace/settings` | 浏览器会话 | GET：**非敏感**配置视图（`{cloudApi,cloudPortal,cloudKeySet:bool,hpcUser,hpcHost,hpcPortal}`，密钥只给 `*KeySet` 布尔）；POST：仅接受上述非敏感字段，验证 + 长度限界 |

失败闭合：403（不可信 Host/Origin）、401/JSON `{"error":"unauthorized"}`（会话无效）、405（错误方法）、400（载荷或字段非法）。grant 端点例外于浏览器会话席位：仅 `x-admin-token` 匹配服务端 0600 存放的密钥。

## 3. 数据落点（现状 = 演示壳内建实现）

- `UQC_WORKSPACE_CONFIG`（默认 `~/.config/unitqc/workspace.json`，0600）：非敏感配置 + 凭据；env 与已存文件字段优先级见 `host.mjs` 头注。
- 同目录 `workspace-access.json`：开通申请账本；`admin-token`：管理员密钥（0600，首次读取时生成）。
- 连接状态探测缓存 15–20 s（cloud 走 SDK 探针，hpc 走 SSH/门户探测路径）。

## 4. 公司内部客户端接管时的替换清单

实现替换时保持 §2 面不变，改动只允许发生在服务端：

1. **会话身份**：`{kind, account}` 中的 `account` 是预留的对外账号字段（≤80 字符自由文本）；内部客户端接入 SSO 后，可由服务端从已认证会话直接解析账号并忽略/覆写该字段，前端不改。
2. **审批流**：`/access/grant` 的 admin-token 换成内部审批系统回调时，验证逻辑放服务端；响应形状不变，审计（谁批的、哪个请求 id）由内部系统持有。
3. **凭据注入**：内部客户端负责把开通结果写进 `UQC_WORKSPACE_CONFIG` 指向的配置（或改由 `host.mjs` 的 env 读取路径），必须保持 0600、不经手浏览器/模型/命令行；建议内部客户端持有该文件唯一的写权。
4. **探测通道**：cloud 的 SDK Socket.IO 探针（`uqc-cloud-probe.py`）与 hpc 的 SSH/门户路径可整体换成内部客户端的统一探测结果缓存；`/status` 响应枚举不得收窄（未知原因归类 `unreachable`/`fetch_failed`）。
5. **失败闭合不变**：任何替换实现仍要保证缺凭据 → `missing_api_key`/未配置状态，禁止把未开通报成已开通；本文档头注的优先级（文件 > env > 默认值）保持。
6. **门禁**：`tests/ui` 对 §2 形状的钉桩不允许删除；更改形状属于合同级变更，同步 UI、插件与文档后重跑 `node --test tests/ui`。
