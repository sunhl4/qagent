# H50 Ollama：模型服务不是企业Agent授权层

对象 `ollama/ollama`；SHA `efabf6bc450454dc856c1f799aac7ea865e3a4cf`，提交2026-10-21T19:00:18-07:00；来源 `/tmp/oss-ollama-ollama`。静态复核chat入口、输入截断与回归测试；未启动模型。根许可以LICENSE为准。

## 实际链

HTTP ChatRequest → JSON/think/top_logprobs检查 → 模型引用解析 → 本地或云端分支 → runner调度、模板、上下文处理 → 生成响应。模型引用带cloud来源时会代理云请求；带远程配置的模型还有独立分支和remotes检查。故“运行Ollama即所有数据完全本地”不是源码支持的普遍结论。

```3024:3033:server/routes.go
	if modelRef.Source == modelSourceCloud {
		req.Model = modelRef.Base
		req.Runner = ""
		if c.GetBool(cloudWebSearchOrchestrationKey) {
			proxyCloudJSONRequestWithPath(c, req, "/api/chat", cloudErrRemoteInferenceUnavailable)
			return
		}
		proxyCloudJSONRequest(c, req, cloudErrRemoteInferenceUnavailable)
		return
	}
```

`genTruncate`位于生成请求的prompt构造路径，控制输入上下文截断，不是工具返回字节预算。chat模板路径也会裁剪历史；保留system及最新user不等价于保留了所有审批依据。公司授权与任务参数必须由宿主持有，不依赖模型是否还记得历史。

## 测试证据

`server/routes_generate_test.go:439-496`用mock runner和小上下文断言旧消息被裁剪、system与最新user保留。测试证明该路径存在消息丢弃，而不是对公司长会话正确性的保证。本轮未执行。

## 公司取舍

公司已有成熟本地模型服务，先测现有DeepSeek端点与DSH的工具调用、流式、取消、上下文和错误合同，无需为采用开源清单而换模型服务。仅在量化部署或开发便携性确有收益时评估Ollama，并限制云/远程模型与网络出口。

对外统一账号、云/HPC开通申请和计费授权位于公司宿主；模型服务的model名、token统计或API兼容不能替代这些。模型生成tool_calls只代表建议，执行仍经严格合同与设备审批。

证据范围：`server/routes.go:636-687,2989-3022,3023-3033,3063-3104`；`server/routes_generate_test.go:439-496`；根LICENSE。本轮未核验整套认证、中间件或生产运维配置。
