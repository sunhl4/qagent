# H26 Anthropic Skills：元数据校验、按需加载与许可证边界

项目 `anthropics/skills`；固定SHA `dbd4588f9e1033efb41dad4bef2f7947c8993d44`，提交2026-10-09T18:45:49+00:00。来源 `/tmp/oss-anthropics-skills`。静态阅读，不安装或执行技能脚本。

## 实际入口和调用链

`spec/agent-skills-spec.md:1-3`仅指向agentskills.io，仓内不是完整规范正文。`template/SKILL.md`给出name/description最小骨架，`skills/skill-creator/SKILL.md`说明编写→测试提示→评估→修订的流程；配套quick_validate.py读取技能目录、解析YAML、校验字段，返回(valid,message)给CLI退出码。

## 三个具体实现

1. quick_validate要求文件存在、以frontmatter开头且是YAML字典；使用safe_load而非执行YAML对象，解析错误返回失败。它是格式检查，不审核脚本内容或数据权限。
2. 允许字段是name、description、license、allowed-tools、metadata、compatibility。自定义企业字段不能任意塞顶层；可以先放metadata并在公司准入阶段另校验。allowed-tools也不能扩大公司DSH工具授权。
3. name限制kebab-case和64字符，description限制尖括号及1024字符；但空字符串在现有条件分支可能不触发名称/描述内容检查，不能称它完整实现规范所有限制。

```41:46:skills/skill-creator/scripts/quick_validate.py
    # Define allowed properties
    ALLOWED_PROPERTIES = {'name', 'description', 'license', 'allowed-tools', 'metadata', 'compatibility'}

    # Check for unexpected properties (excluding nested keys under metadata)
    unexpected_keys = set(frontmatter.keys()) - ALLOWED_PROPERTIES
    if unexpected_keys:
```

## 按需加载和验证

skill-creator正文`:90-113`将metadata、正文、附属资源分三级加载，脚本可能在不把全文给模型的情况下运行。因此“纯文本技能无安全问题”错误：脚本和hook必须单独审查。
本篇以quick_validate作为可执行格式检查器证据，未发现本次范围内独立validator单元测试，明确测试缺口；没有实际运行此脚本或模型评测。

## 许可

多数技能分别带Apache许可；`skills/skill-creator/LICENSE.txt`需按该文件适用。`skills/docx/LICENSE.txt:1-30`明确服务协议及额外限制，不能复制文档技能内容或把它一并称Apache开源。

## 公司映射

- 自有skills保留触发、适用范围、依赖provider、失败行为、来源/版本，metadata扩展先过公司校验。
- 技能不能固化算法名单，也不能授予设备、shell或源码发布权限。
- 入库测试包括无效YAML、额外字段、空name、危险脚本、内部资料混入外部模板。
- DSH仍执行工具循环，技能评测循环只在隔离测试面。

证据：spec/agent-skills-spec.md:1-3；template/SKILL.md:1-5；quick_validate.py:12-39,40-57,59-96；skill-creator/SKILL.md:8-20,90-113；docx/LICENSE.txt:1-30。许可证与格式检查不等于实际任务能力通过。
