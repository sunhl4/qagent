# R-01b · dsh skill 注册

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-26 |
| 角色 | A2 |
| 层 | 进 `dsh --profile qagent`。不是第三套 loop，不重挂 persona |

## 结论

现有 Skill 已挂到 qagent profile。lab / sign 看见量子轨（含 `twin-run`）。algo 只看见造包（`write-provider` / `qchem-scenario`），**看不见 Twin**。空 `qagent` agent preset 仍是 `[]`，没有再挂 `dsh-persona`。

## 怎么挂

Host 的 `skill-filesystem` 已经扫 `$DSH_HOME/skills`。不要在 `agent.cordis.yml` 再挂一层 skill / persona。

| 文件 | 作用 |
|------|------|
| `qagent/profiles/qagent/skill-visibility.json` | 本包拥有的可见集。algo 不含 `twin-run` |
| `qagent/profiles/qagent/skills/` | 相对 symlink，指向 `qagent/skills/<name>` |
| `qagent/scripts/start_runtime.sh` | **skills sync**：按 `QAGENT_PRESET` 把可见 `SKILL.md` 拷进 `$DSH_HOME/skills`。不碰 `.credentials.yaml` |
| `qagent/skills/*/SKILL.md` | 补了 dsh 要的 `name` / `description` frontmatter。没有把 `ionstack_twin_run` 写成 auto-approve |

`dsh --profile qagent` 能列到的，是 sync 之后 `$DSH_HOME/skills` 里那一批。默认 `QAGENT_PRESET=algo`，所以默认 runtime **没有** `twin-run`。

## 可见集

| Skill | lab | sign | algo |
|-------|-----|------|------|
| vibe-across-engines | 是 | 是 | 否 |
| twin-run | 是 | 是 | **否** |
| read-b3 | 是 | 是 | 否 |
| run-frozen-recipe | 是 | 是 | 否 |
| write-provider | 否 | 否 | 是（造包） |
| qchem-scenario | 否 | 否 | 是（造包） |

没有 CAL / shuttle Skill。没有把 TwinRun 注册成官方 Codex MCP。`subagent-codex` 仍是 `permissionMode: never`。Skill 正文仍写：触发也不能绕过 ask。

## 测

```text
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_r01b.py
PYTHONPATH=src python3 tests/run_tests.py
```

`test_r01b.py` 与 `run_tests.py` 均须退出 0。`run_tests.py` 未改（`company_shell` 仍断言 `cordis.patch.yml` 不含 `/Users/`）。调度回收时再挂本测。

## 不做

- 不重挂 persona，不扩 `agent.py`，不发明第三套 loop。
- 不改 `chat.py` / `dsh_session.py` / `run_tests.py` / `PROGRESS.md` / `ionstack.py` / `qdata.py` / customer-shell。
- 不 commit。
