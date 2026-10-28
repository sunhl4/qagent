# H21 mcp-scan / Agent Scan：扫描执行与数据外发边界

原对象 `invariantlabs-ai/mcp-scan`；SHA `73c09662fa9c4afd42716dc42a8f2a0ab55b7229`，提交2026-10-21T09:51:38+02:00；源码包已是agent_scan，来源 `/tmp/oss-invariantlabs-ai-mcp-scan`。根LICENSE Apache-2.0。静态阅读，未运行扫描或启动第三方server。

## 主链路

direct_scan_to_server_config把输入类型转为RemoteServer或StdioServer；后续inspection结果通过build_scan_request转换成版本化API请求，analysis URL强制当前wire版本。扫描不是纯本地字符串lint，可能启动包并发送分析请求。

## 三个具体边界

- npm没有版本时默认latest，命令npx -y；pypi用uvx；OCI用docker run。这是执行第三方程序，不该在生产主机直接扫描任意用户输入。
- build_scan_request仅把顶层path改为home-relative，注释明确component config_path/installation_path仍绝对路径。不能声称扫描器天然完全脱敏。
- analysis version固定2026-07-10，避免自定义URL带旧version造成请求/响应结构错配；异步模式提示结果在Snyk侧处理，提交成功不是本地判分成功。

```20:25:src/agent_scan/direct_scanner.py
def _parse_package_name_version(value: str) -> tuple[str, str]:
    """Split a package specifier into (name, version), handling scoped packages like @scope/pkg@version."""
    if "@" in value.lstrip("@"):
        name, version = value.rsplit("@", 1)
        return name, version
    return value, "latest"
```

## 测试证据

`tests/unit/test_verify_api.py:53-94` mock analyze_machine，断言aiohttp ClientSession trust_env=True、返回路径符合预期。这说明代理环境会参与数据路径；公司provider当前禁用环境代理，不能直接继承扫描器默认设置。

## 公司取舍

开发准入可以借快照、版本化请求和扫描结果分类，但执行扫描在隔离环境、明确允许目录与出网策略下进行。
不能把厂商分析服务当本地能力，更不能把扫描“通过”授予设备权限。
`contracts/`登记工具版本/摘要变化，`tests/`加入恶意描述、远程目录更新、扫描超时和包执行副作用反例。

证据：LICENSE:1-13；direct_scanner.py:1-47；verify_api.py:39-61,69-87,97-105；test_verify_api.py:53-94。未审全部redact/云端分析实现，不保证检测覆盖率。
