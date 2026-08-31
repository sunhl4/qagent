# R-01e · Skill 对齐已接线目录

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | A2 |
| 层 | 进 `dsh --profile qagent`。Skill 是默认建议，不是唯一入口，也不是第三套 loop |

## 结论

`vibe-across-engines` 第 1 步删了「现在都是 reserved」。`qagent_list_engines` 的 `engines[]` 是已接线：五包打头，Cirq 已 wired，`kind=interop`，`provenance` 不是我们的机器，不发 `twin_id`。Pennylane 在 `reserved_engines`，`status=reserved`，不在目录 / `engines[]`。**不算接线 Pennylane**。不算 G0/G1。

## 产品锁

- 三份同文（至少 `qagent_list_engines` 那句）：`qagent/skills/vibe-across-engines/SKILL.md`、`qagent/profiles/qagent/skills/vibe-across-engines/SKILL.md`、`qagent/.dsh-home/profiles/qagent/skills/vibe-across-engines/SKILL.md`。避免 dsh-home 旧文案。
- 保持 R-01 / R-01d：默认建议，不是唯一入口。Skill 触发也不能绕过 ask。frontmatter 仍有 name / description。不写 auto-approve。
- 仍禁止 CAL / shuttle。Aer 无 `twin_id`。上机仍 `ionstack_twin_run` + ask。只有 ionstack TwinRun 能发 `twin_id`。
- 句柄只有 `circuit_id` / `asset_id` / `twin_id`。不发明第四个。
- 不要把 Cirq 标成 reserved。不要宣称 Pennylane 已经接线。

## 怎么挂

profile 与 dsh-home 的 skills 目录指向 `qagent/skills`。改源即三份一起变。若有人改成拷贝，必须同步，避免模型按旧文案把已接包说成 reserved。

## 测

```text
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_r01e.py
PYTHONPATH=src python3 tests/test_r01d.py
PYTHONPATH=src python3 tests/test_r01b.py
```

调度回收时再挂 `run_tests.py`。

## 不做

- 不接线 Pennylane。不改其它 Skill / `skill-visibility.json` / `start_runtime.sh` / `agent.cordis.yml`。
- 不改 `qagent/src/**` / customer-shell / catalog.json / INTERFACES.md / `run_tests.py` / `PROGRESS.md` / `PARALLEL.md`。
- 不铸 `twin_id`，不调 `ionstack_twin_run` 的 `approved=True`。不扩第三套 agent loop。
- 不 commit。
