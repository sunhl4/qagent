---
name: qchem-scenario
description: 改化学 scenario。默认建议，不是唯一入口。Skill 触发也不能绕过 ask。仅 algo 造包。不要上机，不要改核。
---

# 改化学 scenario

默认建议，不是唯一入口。Skill 触发也不能绕过 ask。只在 **algo** preset。造包用。不要改化学核。

## 仓

| 仓 | 路径 | 可改 |
|----|------|------|
| qchem | `/Users/shl/nvidia/qcchem-qml-md` | `scenario`、夹具、测试 |
| Qagent | `/Users/shl/nvidia/qagent` | 只登记、包装 CLI，不 import 核 |
| ionstack | `/Users/shl/Q-software` | **不可见** |

## 逐步命令

1. 读现有 scenario，不要先改核。

   ```bash
   ls /Users/shl/nvidia/qcchem-qml-md
   ```

2. 改 scenario / 夹具。跑：

   ```bash
   # 有 bin 才跑；没有就停并写诚实失败，不要假 asset_id
   /Users/shl/nvidia/qcchem-qml-md/.venv/bin/qchem-run --help
   ```

3. Qagent 侧只许走 `qchem_run` / `qchem_export_parity` 的 CLI 包装。电路只经 pin，出 `asset_id`。

4. 完成：相关单测绿；diff 里没有 `ionstack_twin_run`、没有 `twin_id`、没有 `import qchem`（从 `qagent/src`）。

## 不要做

- 不要改积分、求解器、哈密顿核。
- 不要为了演示伪造 `status=done`。
- 不要上机。上机是第二层 Qagent 的事。
