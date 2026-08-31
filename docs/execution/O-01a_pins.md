# O-01a · pin 复查（冻住，不升）

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | A1 |
| 范围 | `qagent/pins.json` · `profiles/qagent/package.json` · `scripts/bootstrap_wp0.sh` · `profiles/qagent/README.md` · `tests/test_o01a.py` |
| 状态 | 四方一致，冻住。无书面升 pin |

## 冻住版本

| 符号 | 版本 | 出处 |
|------|------|------|
| `deepseek_harness` / `DSH_VER` | `0.1.0-rc.8` | `pins.json` · `bootstrap_wp0.sh` · README `@deepseek-ai/dsh@…` |
| `openai_codex` | `0.147.0` | `pins.json` · `package.json` `@openai/codex` · README |
| `dsh_subagent_codex` | `0.1.0-rc.8` | `pins.json` · `package.json` `@deepseek-ai/dsh-subagent-codex` · README |

## 结论

四方已对齐，本包冻住现网 pin。`pins.json` 字节未改。不写书面升 pin。

若日后任一出处偏离上表，`tests/test_o01a.py` 必须红，并在本笔记改成书面升 pin 清单；禁止静默升级 `package.json` / `bootstrap_wp0.sh` / `pins.json`。

脑仍是 `dsh --profile qagent`。官方 Codex 继续只活在 `dsh-subagent-codex`。不发明第三套 agent loop。不签发 `twin_id`。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_o01a.py
```

## 不做什么

不改 `run_tests.py` / `PROGRESS.md` / `package.json` 依赖 / `bootstrap_wp0.sh` 版本 / `chat.py`。不 commit。
