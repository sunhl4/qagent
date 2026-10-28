# H30 Daytona：公开历史 SDK 与当前私有化边界复核

- 原项目：`daytonaio/daytona`。
- 当前公开分支 SHA：`ec4c21b2d597091ac09ecc278f3bcc172575a987`，2026-06-25T13:16:13+02:00。
- 源码复核改用 README 明确指向的公开标签 `v0.190.0`：`01c502bb1f1ff8f2885d0cd490e043736083dca8`，2026-06-23T15:23:31+02:00。
- 两份来源：`/tmp/oss-daytonaio-daytona` 与 `/tmp/oss-daytonaio-daytona-v0.190.0`。
- 验证：静态阅读历史 Python SDK/测试；不表示已读取当前私有核心。

## 维护与许可事实

当前 README:1-7 明示不再维护、2026年6月核心开发转到私有代码库，并链接历史许可。
这次有维护者明确声明，可以判断该公开分支不再更新；不同于仅凭最后提交日期断言其他项目停推。
历史 Python SDK `libs/sdk-python/src/daytona/_sync/process.py:1-2` 标 Apache-2.0；不能将其扩展为私有最新版许可。

## 历史调用链

`Process.exec()` 构造 ExecuteRequest，包含 command/cwd/timeout/envs。
经生成 API client 的 execute_command 发给 sandbox toolbox，再把响应装为 ExecuteResponse。
`code_run()` 是更高层语言执行入口，可携带参数并返回 charts artifacts。
日志走 WebSocket，复用 httpx 客户端连接池；stdout/stderr 经 demux 分开回调。
证据：历史 `process.py:42-138`。

## 三个重点

1. command timeout 和 HTTP timeout 分离，后者在显式 timeout 基础上多5秒；网络超时不保证沙箱内进程已取消。
2. 响应 exit_code 缺失时回退 additional_properties.code，属于客户端兼容；公司信封不应因此接收未约定字段。
3. response.result 缺失转为空串，artifacts 包含 stdout 和 charts。公司需要区分真实空输出、缺字段和失败，不直接把空串视为完成证据。

```119:124:libs/sdk-python/src/daytona/_sync/process.py
        execute_request = ExecuteRequest(command=command, cwd=cwd, timeout=timeout, envs=env)

        response = self._api_client.execute_command(
            request=execute_request,
            _request_timeout=http_timeout(timeout + 5 if timeout else None),
        )
```

## 测试证据

历史 `libs/sdk-python/tests/test_process.py:21-41` 测正常 exit_code、cwd/env 转发、旧 code 回退。
`:43-71` 测代码运行参数和图表解析。
这些使用 MagicMock API，不证明真实容器隔离、网络治理或任务取消可靠；本次也没有运行测试。

## 对公司的取舍

- 进程结果中退出状态、stdout、图表产物分离，可用于结果分析模板的接口对照。
- 代码分析执行优先复用成熟 HPC 的受管环境；本项目不是必须上 Daytona。
- 生产禁止以任意 shell preset 复刻该执行面；设备仍必须由合同工具提交和审批。
- 平台作业取消、配额和账单以自身服务为准；SDK 超时不是硬件任务失败证明。
- 新测试应覆盖超时后结果未知、图表数据超限、exit_code缺失、跨用户 sandbox引用。

## 证据及不确定项

当前 README:1-7 为维护迁移声明；历史 process.py:1-2,42-79,81-138,140-160 为源码；历史 test_process.py:21-71 为测试。
当前私有核心、其最新服务能力、支持合同和安全更新未验证，不能列为“完整开源可自托管最新版”。
