# H11 Letta：迁移证据与记忆执行围栏

原对象 `letta-ai/letta`，SHA `8816d3a8516893bfdc0fa14bfb1235226012e295`，提交2026-10-18T15:28:01-07:00。该快照README:5明确当前源码在letta-code，历史API在archive分支；这次按明确迁移指引继续读，不把两个仓计成两项目。
伴随源码 `letta-ai/letta-code` SHA `734627d7ea066fd207eacc82bed6075f194f275d`，提交2026-10-21T13:29:32-07:00；来源 `/tmp/oss-letta-ai-letta-code`。静态阅读，未运行Bun/沙箱；许可按两个仓各自LICENSE核查。

## 调用链

`createMemoryConfinementLauncher()`检测沙箱后端后调用WithAvailability实现；后者校验launcher、解析MEMORY_DIR/LETTA_MEMORY_DIR、构建本agent记忆和harness可写root、调用wrapLauncher，最后带sandbox sentinel环境返回。

## 三个实现细节

- normalizeRoot展开~/与$HOME/并resolve；当root名为memory时自动加memory-worktrees。路径扩展是策略范围，不等于只允许一个目录。
- 缺launcher、缺memory root、无backend、无法wrap都抛错，明确不弱策略裸跑。
- memory-confinement.ts文档同时声明可广泛读取宿主、可写harness状态；因此“记忆围栏”不是最小宿主读权限证明。

```73:77:src/permissions/memory-confinement-launcher.ts
  if (!availability.backend) {
    throw new Error(
      `Memory confinement is unavailable: ${availability.reason}.`,
    );
  }
```

## 约束文件与测试

`src/agent/memory-constraints.ts:8-20`描述stage文件字符数、core memory总量、glob和readOnlyFiles；验证脚本伴随Git pre-commit安装。Git hook能辅助写入规范，但不能代替服务端权限，用户可能从其他路径改文件。
`src/memory-confinement.test.ts:9-35`断言Seatbelt launcher、memory-worktrees和sentinel；`:58-77`断言缺root和缺内核后端失败。
这些测试只验证构造与错误，未证明当前WSL宿主实际隔离安全。

## 公司取舍

可借“无隔离后端即拒绝”与记忆写入预算，不能直接继承广泛宿主读取。
公司内部知识保存来源/版本/权限/撤回；Git历史不自动提供企业审计和有效期。
`tests/`加缺sandbox、跨用户memory、符号链接和只读区修改反例；生产DSH唯一，Codex不获得设备工具。

证据：原README:1-37；伴随memory-confinement.ts:13-28；launcher.ts:30-56,59-101；memory-constraints.ts:1-20；memory-confinement.test.ts:9-77。没有把历史MemGPT语义冒充当前实现。
