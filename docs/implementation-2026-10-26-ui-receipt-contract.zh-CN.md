# UI 资源回执契约对齐（2026-10-26，apps/company-workspace 批次）

上一批在 `apps/company-workspace/client.js` 里挂了「资源回执」`conversation.view` 槽位（`company-agent-receipts`），但注册面对的是**假设的** DSH client API。本批逐一在钉死的 DSH 0.1.5-rc.3 客户端源码（`~/.cache/unitqc-company-agent/dsh-runtime/node_modules/.pnpm/node_modules/@deepseek-ai/dsh-client-ui-conversation/lib/{client.js,types}`，以及原生 trajectory 插件同目录）核对真实契约，把接线全部换成已被原生代码实证的模式。范围仅 UI 壳与 tests/ui；Python 侧（contracts/power/src/packages/profiles）留给并行批次，本批未触碰。

## 1. 契约核对结果（全部读自 pinned 运行时源码）

- `ConversationNodeDefinition`（contract/conversation.d.ts）：`kind` 必填；`target` 可选；`match(event)→{id,role:'start'|'update'}|null`；`start(context,match,reader)→State`、`update(context&{state},match)→State`；`publication(match)→'none'|'animation-frame'|'immediate'`（`animation-frame` 需要 requestAnimationFrame，浏览器外自动回落 immediate）；`buildViewNode(context)→ConversationViewNode|null`（`{key,kind,id,target,data}`，trajectory 另加 `anchorSeq/location` 用于排序，属允许的扩展字段）。
- `ConversationViewDefinition/Builder`：`views.register({target,create})`；builder `empty` + `replace({nodes,timeline})` + `apply({upserts,timeline})`，快照始终从节点存储重推导。
- `BoundConversation.target(name)`：返回 `getSnapshot/subscribe` 可观察对象；**subscribe 时激活 target**（懒展开）；未激活时 `getSnapshot()` 为 undefined。
- `conversation.view` 槽位（`ConversationSession` 实现）：renderSlot 只传 `{viewRequest,openView,completeViewRequest}` 与 `{only:active.id}`；tab 列表由 `slots.entries('conversation.view')` 取 `{id, order, label}`（label 经 `resolveSlotLabel`，接受函数）。**没有任何 `useConversation` prop**——组件的会话状态必须走槽位 `inject:(sessionId)=>...` 注入面；原生 trajectory 视图正是这样用 `uiConversation.binding(sessionId).target('trajectory')` 交付可观察对象。
- `resolveActiveView(tabs,selected)`：已选 id 不存在时回落 `DEFAULT_VIEW_ID`；按会话持久化所选 tab——空回执时若返回 null 会留出白板，因此空态必须渲染真实空态面板。
- Durable 工具结果信封（真实事件实测）：`message.content[0]` 是 `tool-result` 包装块，payload 在其内层 `content:[{type:'text',text}]`；`isError` 在包装块上。

## 2. client.js 修改

- 定义/视图对象化：`receiptFold(matches)`（单 callId Context → 单行）、`receiptDefinition`（形状与 trajectoryToolDefinition 对齐）、`receiptBuilder`（trajectory 快照 builder 同型，行按 `anchorSeq` 排序、上限 24 行、`replace` 完整替换/`apply` 增量）。
- `ReceiptView` 组件重写：props 为 `{receipts,viewRequest,completeViewRequest}`；`receipts` 是 inject 交付的 `{getSnapshot,subscribe}` 可观察对象，组件内 `useState+useEffect` 订阅；**不再读取 `useConversation`**；`viewRequest` 在 keyed effect 里完成（不再渲染期写入）；空态渲染 `data-empty` 空态面板。
- `registerReceiptView`：`events.register(receiptDefinition)` + `views.register({target,create})` + `slots.inject('conversation.view',()=>slots.register({name,id:RECEIPT_TARGET,order:20,label:()=>'资源回执',inject:sessionId=>({receipts:binding(sessionId).target(RECEIPT_TARGET)})},ReceiptView))`——inject 面与原生 trajectory 完全一致。
- `receiptText` 递归解包 tool-result 包装块；文本上限 400 字符不变；参数屏蔽词表（`program|path|script|token|secret|password|authorization`）不变。
- `workspace.css`：回执行状态颜色（运行中/已完成/失败）与空态样式收口在同一 token。

## 3. 测试（tests/ui 新增 receipt-contract.test.mjs，29/29 全绿）

- 装载真实 `client.js`/`layout-model.js`：`window.__ModuleLoader__` 垫片 + `vm.compileFunction`（保持宿主 realm，避免跨 realm 断言误报），只垫 `react/jsx-runtime`（注册期无 hooks）、`dsh-client-store`、layout 三个模块边界；未知依赖一律报错。
- 断言真实注册对象等于 pinned 契约：definition 键集合、非公司工具/turn 事件不匹配、view builder 形状与空快照、槽位 order/label/inject 面、subscribe 触发 target 激活、空目标回落 EMPTY。
- 真实引擎事件：spawn pinned node 跑 `tests/fixtures/dsh-lifecycle.mjs`（allow × cloud），把一次真实 `quantum_cloud_submit` 调用的 durable `tool/call`/`tool/result` 事件喂进 match/start/update/buildViewNode/builder——验证完成态、屏蔽词、400 上限、失败态、视图信封、24 行截断。若 python 合同侧被并行批次改造暂时卡住（CLI/合同校验缺 JSON），用例**标记 skip 并如实注明阻塞**，同时用镜像真实信封的 recorded-shape 事件继续把契约点亮（镜像形状显式标注 provenance）。
- 静态门禁：`useConversation` 不再现于 client.js；`viewRequest` 完成是 keyed effect；`data-empty` 空态存在。

## 4. 边界与本批不做

- 全浏览器挂载更显式验证需要 DSH web bundle（slots runtime 不随运行时单独分发）；本批已在注册对象层面用真实契约与真实引擎事件完成可离线验证的最强形态，浏览器挂载验证留给 dsh-desktop 联调批次。
- 本批未动 contracts/src/packages/profiles/knowledge（并行批次域）；`pytest tests/test_plugin_runtime.py tests/test_hpc.py tests/test_cloud.py` 于本批开工时读得 **183 全通过**（并行会话已修复知识夹具），UI node 套件 29/29。
- 中栏仍是只读资源投影；本批不改变 access seam（`/company-workspace/{cloud,hpc}/status|overview`、portal 代理、`/agent/state`）。
