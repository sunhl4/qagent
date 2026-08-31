---
name: write-provider
description: 写 ProblemProvider。默认建议，不是唯一入口。Skill 触发也不能绕过 ask。仅 algo 造包。不可见 Twin。不要注册 TwinRun 当 Codex MCP。
---

# 写 ProblemProvider

默认建议，不是唯一入口。Skill 触发也不能绕过 ask。只在 **algo** preset。这是**造包** Skill，给组内 Cursor / Codex 用。客户和组内 Qagent **不走这条**。

委派 `subagent_codex`；改文件用 `subagent_codex_attended`。

## 仓路径（不要写错仓）

| 仓 | 绝对路径 | 你改什么 |
|----|----------|----------|
| Qagent（本仓） | `/Users/shl/nvidia/qagent` | 合同、夹具、测试、引擎包登记 |
| qdata | `/Users/shl/nvidia/qdata` | 仅当算法 owner 明确要加 provider；**不要从 `qagent/src` import qdata** |
| qchem | `/Users/shl/nvidia/qcchem-qml-md` | scenario，不改核 |
| ionstack | `/Users/shl/Q-software` | **不可见**。本 Skill 全程当它不存在 |

## 硬限制

- 不可见、不可调 `ionstack_twin_run`。不要读 Twin 文档当任务。
- 官方 Codex `permissionMode: never`，`inheritsParentContext: false`。
- attended 先出 `fileChange` 审批，批准前不落 diff。
- 不要注册 TwinRun 当 Codex MCP。
- 句柄只有 `circuit_id` / `asset_id`。本 Skill **不许**出现 `twin_id`。
- 单测绿才算完成，不是口头像 provider。

## 逐步命令

1. **读合同，不要先写代码**

   ```bash
   cd /Users/shl/nvidia/qagent
   sed -n '1,80p' contracts/engines/HOW_TO_ADD.md
   PYTHONPATH=src python3 -c "from qagent.services.engines import list_engines; print([p.id for p in list_engines()])"
   ```

2. **定名字**。provider / fixture 名用 `snake_case`。不要用 `cal`、`shuttle`、`twin`。

3. **只加夹具（默认）**。新人第一次演练写在：

   `qagent/.qagent/spi_scratch/` 或测试用的 fixture 模块。  
   不要改 `qagent/src/qagent/adapters/ionstack.py`。

4. **Algo 子代理改文件**

   - 调用 `subagent_codex_attended`，任务里写清：改哪个文件、完成条件是哪条测试。
   - 等人批准 `fileChange`。
   - 批准前用 `git diff` 确认工作区没有提前落盘。

5. **跑单测**

   ```bash
   cd /Users/shl/nvidia/qagent
   PYTHONPATH=src python3 tests/run_tests.py
   ```

6. **完成条件（全绿才停）**

   - 新 fixture 能被测试 import。
   - `tests/run_tests.py` 退出码 0。
   - `rg ionstack_twin_run` 在本次 diff 里零命中。
   - `rg twin_id` 在本次 diff 里零命中（注释里写「禁止 twin_id」除外）。

## 不要做

- 不要 `import qdata` / `import ionstack` / `import qchem` / `import qiskit`（从 `qagent/src`）。
- 不要为了「看起来接上了」返回假 `status=done`。
- 不要把本 Skill 当客户对话入口。
