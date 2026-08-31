# C-01 · 3080 客户面文案

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-26 |
| 角色 | P |
| 范围 | `qagent/apps/customer-shell/*` · `qagent/tests/test_c01.py` |
| 状态 | 代码落地，文本测绿 |

## 产品锁

- 欢迎语和输入框用平常话交办。不把 `a2_chem_pes` 等内部 recipe 名写成必填标签。
- 主面不是模型选择墙：标题固定「你想做什么？」。模型地址 / 模型池 / 软件包目录仍留给组内，收在设置里的「组内：模型与软件包目录」，不是进对话的第一道墙。
- 在办、批准上机、先不上机保留。仍走 `send("批准")` / `send("先不批")`。没有三房间，没有 `btn-twin`，没有 Finder / 工作区门槛。
- `hpc_secret` / `quantum_secret` / `llm_api_key` 是 password。页面只画 placeholder「已保存」，不从 `/api/workplace` 回填值。

## G2 演示（客户角色，约 20 分钟）

1. 打开 3080。不要先选模型、不要报 recipe 名。一句话说要算什么。
2. 右侧在办出现待批则点「批准上机」。先不上机走同一对话，不新开 loop。
3. 导出回执后，另一台机器跑 `python3 scripts/verify_receipt.py`。
4. 打开设置：密钥栏只见「已保存」，看不见超算密码值。

## 不做什么

不改 `chat.py` / `dsh_session.py` / `assignment.py` / workplace。不加第三套 agent loop。不 commit。`run_tests.py` / `PROGRESS.md` 留给调度挂。
