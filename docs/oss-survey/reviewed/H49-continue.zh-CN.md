# H49 Continue：上下文服务的数据边界

对象 `continuedev/continue`；SHA `5522c6f44ca0ac3528b37244818fbfa39b5af470`，提交2026-07-20T21:00:09-07:00；来源 `/tmp/oss-continuedev-continue`。静态复核HTTP上下文provider与其单测；未启动IDE或发送公司对话。许可证按根LICENSE。

## 调用链

用户选择HTTP上下文provider → 配置URL及headers → 获取当前工作区路径 → POST query/fullInput/options/workspacePath → 解析响应 → 映射为ContextItem。允许自定义服务整合公司知识检索，是可借鉴的解耦方式，但数据最小化应逐字段设计。

`getWorkspacePath`仅在`isLocalhost(url.hostname)`成立时返回匹配当前文件的工作区；源码注释说明该检查也涵盖其他local地址。这只是工作区路径的选择条件，不能泛化为完整对话不外发。

```60:65:core/context/providers/HttpContextProvider.ts
      body: JSON.stringify({
        query: query || "",
        fullInput: extras.fullInput,
        options: this.options.options,
        workspacePath: await this.getWorkspacePath(extras.ide, parsedUrl),
      }),
```

无论是否本地目标，`fullInput`都在请求中。fetch和`response.json()`位于后续映射try/catch之外，因此网络/JSON解析错误会向外传播；catch只捕获映射等错误，还会将整个json写warning。这是此方法的局部错误边界，不能据此推断上层没有捕获。

## 测试证据

`core/context/providers/HttpContextProvider.test.ts:37-109`检查单项及null/缺失uri转换。它不能证明服务端内容可信或权限完整，也未提供此路径的敏感数据外发防护证明。本轮未运行测试。

## 公司适配

知识服务由宿主以受信任租户/账号执行检索，不让模型提供身份；默认只发送查询和必要过滤字段，避免完整对话、内部代码或凭据被隐式传给任意HTTP目标。结果保持短摘要、访问控制后的来源引用和截断说明，完整正文留在受控存储。

错误日志只记录允许字段和关联标识，不输出原始json。客户端显示“检索失败”与“平台离线”要区分；知识接口可用不代表云/HPC提交通道已登记。借鉴ContextItem展示协议即可，Continue的Agent能力不接入为第二生产循环。

证据范围：`core/context/providers/HttpContextProvider.ts:18-30,48-67,69-89`；`core/context/providers/HttpContextProvider.test.ts:37-109`；根LICENSE。此结论限于HTTP provider，不涵盖全部Continue上下文来源。
