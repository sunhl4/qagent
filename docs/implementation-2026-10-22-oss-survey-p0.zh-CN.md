# oss-survey P0 落地实现（2026-10-22）

按 `docs/oss-survey/04-工程衔接建议.zh-CN.md` 的 P0 清单实施，遵循开发顺序：合同 → Python adapter → DSH 插件（无需改动）→ 测试。全局基线与回归：`tests/` 全量 **792 通过 / 0 失败**（含本批 22 项新门禁）。本批不改变 v0.8 架构、不放松任何硬规则；fail-closed、三句柄、设备/HPC/云批准位全部保留。

## 1. 合同层变更（真源）

- `contracts/results.json`：新增 `receipts` 块——回执契约：字段白名单、`records = [dispatch, outcome]`、`statuses = [dispatched, ok, refused, error]`、`execution_states = [dispatched, completed, unknown]`、`binding_operations = [cloud.submit, device.run, hpc.submit]`、单记录 1600B、单文件 256KiB、最多 14 个文件、证据新鲜度 3600s、主体最 253B。
- `contracts/tools.json`：`company_capabilities` 输出扩展为四层判定的能力清单：
  - 顶层新增 `identity`（`subject` 归因主体 + `profile`）与 `approvals`（可见且当前判定为 `ask` 的工具名列表，执行期授权层）；
  - 每能力行新增 `evidence`（`state: unavailable|none|ok|failure|stale`、`tool`、`request_id`、`age_seconds`、`digest_match: current|stale|unavailable`）——真实执行证据层，带时间与合同 digest 版本。

## 2. Python adapter 变更

- 新增 `src/company_agent/receipts.py`：工作区之外的追加式 JSONL 回执账本。
  - `record_dispatch()`：外发前落盘 locator；绑定操作失败即拒绝外发（fail-closed），消息 `provider dispatch receipt is unavailable; request not sent`，不接近网络一次字节。
  - `record_outcome()`：终态记录（best-effort 决不覆盖真实结果）；`ok` ⇒ `completed`；**refused**（平台权威拒绝，HTTP 4xx / 401/403 / 协议拒绝）⇒ 终态为已知拒绝，不需要对账；其余（5xx、传输/超时、内容校验失败）⇒ `unknown`，只能对账。
  - 身份归因 `subject = user@host`（畸形值回退 `unknown@unknown`），绝不写参数、结果或凭据；O_APPEND 单条原子写入，0700 目录 / 0600 文件。
  - 保留策略：按日期分文件、`max_file_bytes` 轮转、`max_files` 逐出最旧；读取跳过撕裂行，限定条数与文件数。
  - `evidence(tool_names)`：能力证据判定——`ok`（新 + 当前 digest）、`stale`（超龄或 digest 变更）、`failure`（最后记录为失败）、`none`（无记录）、`unavailable`（存储不可读）。凭据配置永远不能替代真实执行证据。
- `providers.py`：
  - 派发前钩子 `requires_dispatch_record()` + `record_dispatch()`（见上）。
  - 终态钩子 `record_outcome()`；`ProviderError.decisive` 标记权威拒绝（协议 `ok:false`、HTTP 401/403/4xx），5xx、传输错误、响应丢失保持不确定语义；`outcome unknown; do not retry automatically` 文案仅用于未确认路径，拒绝路径原样透出平台答复。
- `invoke.py::_capability_payload`：接入 `identity` / `approvals` / 每行 `evidence`；存储异常只降级 `evidence.state=unavailable`，决不让能力清单失败或伪造在线。
- `cli.py`：新增 `reconcile` 子命令（`--request-id`、`--limit`）：对账入口输出 `unknown` 时间线 + `recent` 记录 + 固定说明（未知结果必须用业务上下文重查平台状态、禁止自动重提）。

## 3. DSH 插件层

零改动：`company_capabilities` 由合同驱动注册，`runtime.js` 的 `dshSchema`/`validateInvocationResult`/渲染上限自动覆盖新 schema；插件无第二会话循环。

## 4. 验收反例（tests/test_receipts.py）

按 04-建议「验收反例」逐条落入门禁：

1. 无回执的外发必须没有字节出机（`refuse _persist` ⇒ `requests == []`）。
2. 平台受理后回包丢失 ⇒ `unknown` 记录 + reconcile 旗标，禁止静默重提；绑定派发无终态（进程中断）同样被旗标。
3. 平台权威拒绝（4xx / `ok:false`）⇒ `refused`，决不伪装成 `unknown`。
4. `company_capabilities`：boot 无批准项；凭据注入只给 `configured_unverified`；成功执行把对应能力证据提升为 `ok`（带 request_id、digest、时效）；digest 过期或超龄转 `stale`；存储不可读转 `unavailable`，清单本身不失败。
5. 合同校验：receipts 块损坏 ⇒ 派发被拒、读取降级，不产出任何伪造状态。
6. 轮转与逐出：超 256KiB 滚动新文件；超过 14 文件预算逐出最旧。

另外既有 P0-2 门禁保持：`--approved` 仅在 `COMPANY_AGENT_APPROVAL_CONTEXT=dsh` 且完整 profile 可用；审批无缓存（每次调用独立 CLI 进程 + `twice` 生命周期用例证明 ask 每次发生）；审批理由绑定 tool + circuit_id + shots 不可变参数摘要。

## 5. 后续（P1/P2，未实施）

- 会话内以句柄定位大产物 + 分析模板输出口径（04-建议 §3.1）：合同面先行。
- 知识入库来源/权限/有效期的撤回门禁扩展（§3.2）。
- 工作台订阅 `company_capabilities` / `reconcile` 白名单投影（§5.1）——工作台现有 `/cloud/status`、`/hpc/status` 探测可信，仍需与 DSH 会话工具可见性合并展示。
