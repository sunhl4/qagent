# H46 Open WebUI：工具权限与品牌许可需分别评估

对象 `open-webui/open-webui`；SHA `91ea4e3421d1d8069f13d4a463fcb5986d94ea60`，提交2026-10-16T06:46:08-05:00；来源 `/tmp/oss-open-webui-open-webui`。静态复核本地工具加载与MCP客户端；未启动服务或测试租户隔离。

## 工具调用与信任边界

`get_tools`先按插件开关过滤工具 → 获取用户含继承的群组 → 批量加载本地工具 → 检查所有者/资源read权限/管理员旁路 → 动态载入工具模块 → 注入宿主用户和配置 → 移除模型schema里的内部参数 → 注册callable。read权限在此承担工具加载许可，不能直接等价为公司外部计算资源的执行授权。

本地工具代码会被动态载入，属于受信任服务端扩展，不是沙箱中的任意用户代码。管理员旁路有显式开关；内部`__user__`等由宿主注入，是公司可借鉴的“模型不能自报身份”原则。名称冲突采用加前缀策略，公司合同工具名则必须稳定且未知名称拒绝。

```100:103:backend/open_webui/utils/mcp/client.py
            else:
                url = urlsplit(params.url)
                if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password:
                    return ElicitResult(action='cancel')
```

MCP elicitation会检查URL格式或表单schema，回答不合法/异常时cancel；表单验证使用空引用registry避免抓取服务端schema引用。这不代表任意http(s)目标已完成网络出口授权。连接使用streamable HTTP、AsyncExitStack清理和初始化超时，工具列表处理分页。

`get_tools`所读远程分支明确是OpenAPI；MCP客户端是另一条链。不能把本地/该OpenAPI分支的ACL检查泛化为所有MCP路由均已隔离，完整判断须继续追踪各调用者。

## 许可与测试缺口

根LICENSE是Open WebUI License，品牌修改限制有滚动30天不超过50位自然人、事先书面许可、企业许可三类例外。旧结论“任何改名都必须付费”错误；商业白标选型应按实际人数、分发和许可逐项核实。历史文件另有LICENSE_HISTORY，不能统一标MIT。

本次`git ls-files`按tool/MCP测试名称检索未找到直接对应测试，尚无本轮可引用的该链行为单测；这不证明仓库完全没有测试。需要补充工具所有者、继承群组、管理员开关、远程连接和恶意elicitation矩阵；本轮未执行。

## 公司取舍

借鉴中栏资源浏览、设置与工具接入交互，保留DSH唯一Runtime。企业统一身份在宿主做绑定，用户只申请开通云/HPC，不接收共享平台密钥；工具可见性与平台授权同源，但执行前仍独立校验。网页嵌入成功不表示API作业链已验证。

证据范围：`backend/open_webui/utils/tools.py:345-385,387-430,460-505`；`backend/open_webui/utils/mcp/client.py:27-49,97-127,129-178`；`LICENSE:20-37`。工具链和MCP全局隔离仍为显式验证缺口。
