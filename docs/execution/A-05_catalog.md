# A-05 · 资产目录

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-26 |
| 角色 | S1 |
| 范围 | `qagent/src/qagent/adapters/qdata.py`（`list_assets` / `list_providers`）· `qagent/contracts/tools/qdata_list_assets.json` · `qagent/tests/test_a05.py` |
| 未改 | `catalog.json` 引擎表 · `engines.py` · `run_tests.py` · `PROGRESS.md` · `chat.py` · `ionstack.py` |

## 行为

| 条件 | 结果 |
|------|------|
| `qdata_list_assets` | 短列表，每行 `name` + `kind`。recipe 带 recipe id；card 带 `asset_id`；知识条只带文件名。合计 ≤20 行，字符串 ≤80 |
| 存里有 Pauli / bitstrings / QASM / `summary` | 不进目录。行键只有 `kind` / `name` / `asset_id` / `recipe` |
| 知识条 | 只列 `handbooks/` 与 `QAGENT_KNOWLEDGE_PATH` 的 `.md` / `.txt` 相对路径。不读正文 |
| `qdata_list_providers` | 仍是 allowlist 五个短名。不编第六个配方 |
| `qagent_list_engines` | 仍读 catalog 五包。现在全是 `wired`。若有 `reserved` 会原样保留。不造第六包 |

句柄仍是 `circuit_id` / `asset_id` / `twin_id`。目录不发 `twin_id`。`qdata.py` 源码也不写这个字段名。

## 测

```bash
cd qagent
PYTHONPATH=src python3 tests/test_a05.py
PYTHONPATH=src python3 tests/run_tests.py
```

环境在 `test_a05.py` 里隔离 store / 知识根。超长 store 用 30 张肥卡断言截断。

## 剩

- `services/engines.py` 没改：catalog 已是五包 `wired`，对齐测试只断言透传。
- 活知识库长目录仍靠 5 个 knowledge 槽 + 总 20 行封顶。
- `tests/run_tests.py` / `PROGRESS.md` 留给调度挂测。
