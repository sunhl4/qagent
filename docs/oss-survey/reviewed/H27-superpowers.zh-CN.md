# H27 Superpowers：会话hook注入与流程技能

项目 `obra/superpowers`；SHA `2ce8aa15d05bd57213e6f746f953aafb7ded7a8b`，提交2026-10-21T14:00:49-07:00；来源 `/tmp/oss-obra-superpowers`。根LICENSE MIT。静态阅读脚本和测试，未安装hook。

## 主链路

`hooks/session-start`从脚本路径确定PLUGIN_ROOT，读取using-superpowers技能，转义成JSON字符串，按Cursor/Claude/Copilot等环境输出对应上下文键。其他技能按索引继续加载，而非把所有内容塞进每轮。

## 三个细节

- PATH不可用时用Bash内建读取和参数替换，避免依赖dirname/cat；这提高启动可靠性，但并非内容安全审查。
- JSON转义处理反斜线、引号和换行等；不同宿主字段只发一份，避免Claude重复注入。不能推断未知DSH也自动兼容这些hook。
- 读不到索引时注入错误字符串，而不是脚本失败；公司可信技能加载失败应显示不可用，不能当成功挂载。

```20:25:hooks/session-start
skill_md="${PLUGIN_ROOT}/skills/using-superpowers/SKILL.md"
if [ -r "$skill_md" ]; then
  using_superpowers_content="$(<"$skill_md")"
else
  using_superpowers_content="Error reading using-superpowers skill"
fi
```

## 测试

`tests/hooks/test-session-start.sh:33-85`在隔离env中执行并解析JSON，检查nested和top-level字段不能混用；脚本有PASS/FAIL聚合和临时目录清理。它验证输出协议，不审查技能指令是否越权；未运行。

## 公司落点

复用索引式加载、来源版本和格式测试，不引导模型安装其他宿主runtime。
`profiles/`只挂受管skill，索引内容审核后才能进入可信指令区；hook脚本本身也是准入对象。
测试缺文件、错误宿主字段、重复注入、危险命令、未授权技能与含内部源码的资源。
设备审批与算法目录不因“工程纪律技能”改变，禁止技能打开shell preset绕过生产限制。

证据：hooks/session-start:6-25,27-42,44-85；tests/hooks/test-session-start.sh:1-24,33-85；LICENSE:1-21。没有使用“最大技能库”等无法由此快照证明的排名描述。
