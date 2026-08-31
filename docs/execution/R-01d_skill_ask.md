# R-01d · Skill 触发不绕过 ask

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | A2 |
| 层 | 进 `dsh --profile qagent`。Skill 是默认建议，不是唯一入口，也不是第三套 loop |

## 结论

Skill 只提示该调哪条工具。真正过不过仍走 `decide()` / `invoke()`。**Skill 触发也不能绕过 ask**。未批准的 `ionstack_twin_run` 停在 `needs_ask`，不发 `twin_id`。

## 产品锁

- 每份 `qagent/skills/*/SKILL.md` 写明：默认建议，不是唯一入口（或等价句）。
- `twin-run` 正文写：Skill 触发不能绕过 ask。其它 Skill 缺这句的补一句。不写 auto-approve / 自动批准 TwinRun。
- `decide("ionstack_twin_run", "lab", {"shots": 1000})` 是 `ask`。algo 同参是 `deny`。
- `invoke("ionstack_twin_run", "lab", …)` 未带 `approved=True` → `status=needs_ask`，payload 无 `twin_id`。
- 脑仍是 `dsh --profile qagent`。不发明第三套 agent loop。只有 ionstack TwinRun 能发 `twin_id`。

## 怎么挂

`qagent/profiles/qagent/skills/` 是指向 `qagent/skills/` 的 symlink。改 Skill 只改 `qagent/skills`。`start_runtime.sh` 再 sync 进 `$DSH_HOME/skills`。不改 `.dsh-home/` 副本。

## 测

```text
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_r01d.py
```

调度回收时再挂 `run_tests.py`。

## 不做

- 不改 `run_tests.py` / `PROGRESS.md` / `skill-visibility.json` / `policy.json` / `agent.cordis.yml` / `chat.py` / `dsh_session.py` / `Q-*.json`。
- 不铸 `twin_id`，不调 `ionstack_twin_run` 的 `approved=True`。
- 不 commit。
