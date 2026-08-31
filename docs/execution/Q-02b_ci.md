# Q-02b · PR CI

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-26 |
| 角色 | Q |
| 范围 | `.github/workflows/qagent-eval.yml` · `qagent/tests/test_q02b.py` |

## 做了什么

仓根 `.github/workflows/qagent-eval.yml` 每 PR（以及 push）在 `working-directory: qagent` 跑两步：

```text
PYTHONPATH=src python3 tests/run_tests.py
PYTHONPATH=src python3 tests/run_qagent_vs_codex.py
```

第一句覆盖 E01–E21（以及已挂进 `run_tests.py` 的合同测，含 Q-01 诚实：伪造 twin / 跳过 ask / CAL = 红）。第二句打 Q-01 对照表；任一条 Q-h* 实跑失败则非零退出。Q-h06 `needs live` skip 不算硬轨红。

不声明 `secrets.*`，不 `upload-artifact`，`checkout` 关 `persist-credentials`。不训模型。不 spawn 官方 Codex。不为 Codex 发明 `twin_id`。

`qagent/.github/workflows/eval.yml` 仍是旧本地脚本入口；本包门禁以仓根这份为准。

未改 `run_qagent_vs_codex.py`：默认已按硬轨计退出码，不需要 `--hard-rail`。

## 测

```text
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_q02b.py
PYTHONPATH=src python3 tests/run_qagent_vs_codex.py
```

`test_q02b.py` 断言工作流文件存在、含上述两句、cwd 是 `qagent`。`run_qagent_vs_codex.py` 须退出 0（Q-h06 skip 可）。`run_tests.py` 未改；调度回收时再挂本测。

## 不做

- 不改 `product_eval.py` / `run_tests.py` / `PROGRESS.md` / `chat.py` / adapters / customer-shell。
- 不 commit。
