# R-02 · 灵活选工具

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | A2 |
| 层 | 进 `dsh --profile qagent`。不是第三套 loop，不重挂 persona |

## 结论

未知工具 / 无规则仍 **deny**（`decide` 末尾 fail-closed，未改弱）。灵活条用已有 Q-f01「先别上机，只估计 H₂」：`ionstack_compile_estimate` 有 `makespan_ns`、无签收 `ok`、无 `twin_id`。估计不能跳过 TwinRun 的 ask。系统轨写在 `qagent/profiles/qagent/rails.md`：**资产优先**，**禁止编造 twin_id**。空 `qagent` agent preset 仍是 `[]`。

## 怎么落地

| 文件 | 作用 |
|------|------|
| `qagent/src/qagent/services/policy.py` | 已 fail-closed。未改 |
| `qagent/contracts/eval/Q-f01.json` | 已有「只估计不上机」。未加 Q-f06（30 Q id 冻结） |
| `qagent/profiles/qagent/rails.md` | 系统提示。不进 `agent.cordis.yml` / `preset.yml` |
| `qagent/tests/test_r02.py` | 未知工具 deny、估计合同、TwinRun 仍 ask、rails / note 在 |

`dsh --profile qagent` 的脑仍是这一套。造包时 TwinRun 不可见；lab 上机仍要批准。

## 测

```text
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_r02.py
```

`test_r02.py` 须退出 0。未改 `run_tests.py` / `PROGRESS.md` / `qagent-eval.yml`。调度回收时再挂本测。

## 不做

- 不重挂 persona，不扩 `agent.py`，不发明第三套 loop，不铸造 `twin_id`。
- 不改 `agent.cordis.yml` / `preset.yml` / `policy.json` / `Q-*.json` / `chat.py` / `dsh_session.py` / workplace / customer-shell。
- 不 commit。
