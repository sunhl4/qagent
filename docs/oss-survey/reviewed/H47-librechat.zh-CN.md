# H47 LibreChat：工具角色授权复核

- 仓库：`danny-avila/LibreChat`。
- SHA：`e081b566a42d3a83b8102157bd7806cf4ff63b17`，提交 2026-10-17T00:30:44-04:00。
- 来源：`/tmp/oss-danny-avila-LibreChat`。
- 验证：静态源码/测试阅读；未运行服务、模型和鉴权攻击。

## 实现链路

`ToolService.js` 从 `@librechat/api` 导入工具角色检查、MCP 授权上下文、工具审批 metadata 和内容过滤器。不能仅凭这些导入证明整个链路安全，因此本篇深入角色检查函数。

`packages/api/src/tools/rolePermissions.ts` 将工具名映射到角色权限，`checkToolRolePermission()` 调用请求级缓存的 `checkAccessWithRequestCache()` 检查 USE 权限；批量解析函数先筛选当前配置所请求工具，再返回同步 predicate 给 loader 使用。

## 三个关键机制

1. **部署开关与角色授权同时成立。** 文件 `:13-22` 区分 instance-wide AgentCapabilities 和 per-role grant。公司应同样区分“该能力安装了”和“此用户可用”，不能只依据全局配置显示已开通。
2. **异常拒绝与异常中止有区别。** `:65-101` 默认查权限失败返回 false；但 `throwOnError` 允许变更配置的调用方中止写入。若把权限库故障解释成“过滤掉工具并保存新配置”，会静默损坏用户配置。
3. **未列入映射的工具不由这层拦截。** `:118-153` 明确无角色映射的工具返回 true。因此这只是部分 built-in 工具的角色门，不是所有 MCP 工具默认失败闭合的证明；公司仍需未知工具 deny。

## 上传也属于同一权限边界

`toolResourceRolePermissions` 将 file_search、execute_code 和 code_interpreter 资源映射到相同使用权限；`checkToolResourceUploadPermission()` 在上传入口复用检查。

这防止只禁止调用，却仍允许为被禁工具上传资料。公司对内部知识/算法材料同样要覆盖读取、上传、检索、摘要和导出，不只限制按钮。

## 精确源码

```72:78:packages/api/src/tools/rolePermissions.ts
export async function checkToolRolePermission({
  req,
  user,
  permissionType,
  getRoleByName,
  context = 'toolRolePermissions',
  throwOnError = false,
```

## 已有测试及未覆盖边界

`packages/api/src/tools/rolePermissions.spec.ts:28-52` 断言 built-in 工具、代码资源和旧 retrieval 别名映射；`:55-96` 分别测试授权、明确拒绝、权限库异常时拒绝。

这些测试是具体的授权反例，不证明完整应用不存在越权。本轮未执行测试，也未审核全部 MCP token 交换、数据库租户过滤和 UI 同步路径。

## 对公司的落点

- `contracts/capabilities.json` 与 provider 状态应区分部署和主体授权，现有 preset 不足以表达全部企业身份维度。
- `apps/company-workspace/host.mjs` 的本机全局开通状态不能直接推广为多租户；接入平台账号时逐用户绑定。
- `src/company_agent/invoke.py` 执行期继续校验已登记工具，不能采用该局部 helper 的 unknown=true 默认。
- 测试覆盖权限存储异常、跨租户资产、上传与执行两条入口，不以 UI 隐藏作为证据。

## 取舍

借鉴部署开关×角色授权及写入失败语义，不整套替换公司前端或运行时。已核根 `LICENSE:1-21` 为 MIT，Copyright 2026 LibreChat；具体引入模块的依赖许可仍需另查，许可不等于产品已验收。

## 证据

`api/server/services/ToolService.js:1-80`；`packages/api/src/tools/rolePermissions.ts:13-45,65-101,118-153,163-190`；`packages/api/src/tools/rolePermissions.spec.ts:28-96`。
