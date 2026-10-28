# H04 OpenHands：桌面/Web 与远程运行事件桥

项目 `All-Hands-AI/OpenHands`；SHA `f4ae000f452bceae3478dfdd404386b1a131e4c5`，提交2026-10-22T00:51:20+00:00；来源 `/tmp/oss-All-Hands-AI-OpenHands`。静态阅读，未运行服务器。当前仓以TS界面/客户端集成为主，不能沿用历史Python runtime路径推断。

## 真实链路

`useRespondToConfirmation` 接收conversationId、conversationUrl、sessionApiKey和accept，构造请求后调用EventService。EventService经typed ConversationClient把审批发往该conversation的runtime；历史事件则在cloud模式调用App API，local模式用RemoteEventsList。

## 机制和失败路径

- App API bearer与运行时session key是不同认证域；界面能读历史不等于能批准运行工具。这直接对应公司“网页可打开但对话没执行通道”的问题。
- 事件分页接收limit、pageId、timestamp筛选；cloud limit限制100。旧服务不支持筛选时，非strict路径返回空页并停止分页，strict路径抛错；可避免无限重复第一页，但也可能使历史不完整，UI必须说明。
- 审批mutation仅发送决定，不在前端执行任务；公司三栏界面也应走后端策略，不用UI state授权。

```21:23:src/hooks/mutation/use-respond-to-confirmation.ts
      const request: ConfirmationResponseRequest = {
        accept,
      };
```

## 测试

`src/api/event-service/event-service.api.test.ts:98-127`验证cloud确认直接用runtime typed client、不走cloud proxy；`:130-155`验证local同类路径和没有session key的传参。测试使用mock，不代表真实CORS/认证安全已验证。

## 公司取舍

借鉴跨端认证域、事件分页完整性和审批桥；不引第二Agent runtime。工作台开通状态、DSH工具注册、平台权限应分别显示。插件保持转调company-agent invoke；审批恢复绑定用户和参数，设备policy不放宽。
建议回归：历史服务不可用、运行时过期key、分页降级、批准发错conversation、断线恢复重复回复。

证据：hook:1-32；event-service.api.ts:17-55,71-134,137-152；event-service.api.test.ts:98-155；根LICENSE。未审外置agent-server实现，不能宣称本仓证明内核沙箱行为。
