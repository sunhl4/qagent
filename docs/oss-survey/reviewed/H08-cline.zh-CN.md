# H08 Cline：消息检查点映射与审批界面边界

项目 `cline/cline`；SHA `c441897f11f658f978a00678f045670c1ab2b60d`，提交2026-10-21T17:47:26-07:00；来源 `/tmp/oss-cline-cline`。根LICENSE Apache-2.0。静态阅读，未运行扩展。

## 调用链与机制

SDK消息流先判断可见用户task/user_feedback，再剔除对followup/mistake_limit问题的回答，才计算checkpoint run count。按run查消息使用相同判定，避免UI定位到错误回合。

`isCheckpointAnswerMessage()` 从当前feedback向前查，跳过checkpoint_created；遇ask检查其类型，遇另一可见用户消息停止。这说明普通回答并不总是新任务。
`getCheckpointRunCountForMessage()` 从头累计有效任务，`findVisibleCheckpointUserMessageByRun()`逆向映射计数到消息；二者必须一致。

```3:5:apps/vscode/src/sdk/sdk-checkpoints.ts
export function isVisibleCheckpointUserMessage(message: ClineMessage): boolean {
	return message.type === "say" && (message.say === "task" || message.say === "user_feedback")
}
```

## 审批UI不是授权源

AutoApproveBar从全局actions展示开关，并有cloudAutoApprove展示分支。该UI文案不能单独证明后端所有工具总会免审；旧稿把一行tooltip扩大成整套后端结论过度。本项目无论云端桌面均保持设备ask/deny。

MCP per-tool autoApprove位可作产品交互参考，但不能写成公司设备免审设置。代码检查点也仅是本地工作区/消息关系，不能回滚QPU任务。

## 测试证据

`apps/vscode/src/sdk/sdk-checkpoints.test.ts:51-81`断言只认可用户消息、按run找到正确任务、followup答案不算新run。它验证UI映射，不验证文件快照事务和外部作业回滚。

## 公司落点

- 中栏历史列表对齐真实任务关联，右栏回答审批问题不自动生成新提交。
- 插件输出只包含受管状态，UI检查点只读比较，重提必须新授权。
- 回归覆盖异步消息插入、审批回复、断线重连的run映射与重复事件。

证据：sdk-checkpoints.ts:3-27,29-45,47-63；sdk-checkpoints.test.ts:51-81；AutoApproveBar.tsx:15-33；LICENSE。未审全部Cline runtime及云后端。
