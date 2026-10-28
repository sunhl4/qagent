# H02 gptme：确认 hook 与默认放行边界

项目 `gptme/gptme`；SHA `fc2c17be32f3550d66351aaff3b45c21ccc05eab`；提交2026-10-21T19:23:48+02:00；来源 `/tmp/oss-gptme-gptme`。静态源码/测试阅读，未运行。许可根 LICENSE。

## 主链路

执行器调用 get_confirmation，若未显式传 ToolUse 则从 context 获取；优先识别同一 ToolUse 已确认的嵌套执行，再按优先级遍历启用的 TOOL_CONFIRM hooks，返回 confirm/skip/edit。CLI、server、auto 是可插拔确认面，不是单一部署保证。

## 实现细节与失败行为

- `ContextVar` 分隔 auto override/count 和 preconfirmed_tool_use，减少并发请求共享确认状态；preconfirmed contextmanager finally reset，嵌套同一对象不重复询问。
- default_confirm=True：无上下文、无启用 hook、所有 hook 返回 None 或不支持类型，最后都可能确认。hook抛异常才直接 skip。因此“hook体系”不自动等于失败闭合。
- boolean 返回兼容为 confirm/skip；EDIT 带 edited_content。公司不能让改参自动沿用旧设备批准。

```186:191:gptme/hooks/confirm.py
def get_confirmation(
    tool_use: "ToolUse | None" = None,
    preview: str | None = None,
    workspace: Path | None = None,
    default_confirm: bool = True,
) -> ConfirmationResult:
```

## 测试

`gptme/hooks/tests/test_confirm.py:55-76` 对无hook分别测试 default_confirm=True确认与False跳过；`:78-119` 测已注册confirm/skip hook。测试明确证明默认行为取决于参数，不可笼统称无hook永远拒绝或永远允许。

## 公司映射

1. `policy.py` 保持无效合同/未知工具deny，缺少确认hook应阻断而非采用默认True。
2. `runtime.js` 的人工批准来源不可由工具参数伪造，嵌套执行关联要绑定不可变参数。
3. 生命周期测试覆盖无hook、返回None、错类型、异常、嵌套不同ToolUse和修改参数。
4. 提示词拒绝文案只能解释，不能代替执行前策略。

## 取舍

借 context作用域和确认测试；不引 gptme 循环、自动批准计数或开放shell。
证据：`confirm.py:29-89,186-275`、`gptme/hooks/tests/test_confirm.py:55-119`、LICENSE。未审全部工具执行器与服务器权限，不能宣称多租户安全已经保证。
