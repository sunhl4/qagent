# I-face · list_engines 行对齐 Pennylane reserved

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | I-face |
| 范围 | `qagent/INTERFACES.md` 的 `qagent_list_engines` 行 · 本笔记 · `qagent/tests/test_iface_pl.py` |
| 层 | 接口文案。不是接线。不是客户 Agent，不是第三套 loop |
| 状态 | `list_engines` 行写 Pennylane 在 `reserved_engines`、不在 ids。不算接线。 |

## 产品锁

- `invoke("qagent_list_engines")` 那一行：五包打头且 `wired`；Cirq 在其后，`kind=interop`，不发 `twin_id`。
- Pennylane 在 `reserved_engines`，不在 ids。不算接线。
- 不要把 Pennylane 写成已接线。不要把 Cirq 写回 reserved。
- 句柄只有 `circuit_id` / `asset_id` / `twin_id`。不发明第四个。

## 改了哪一行

`qagent/INTERFACES.md`「现在能跑」表里 `invoke("qagent_list_engines")` 行：在 Cirq interop 句后补「Pennylane 在 `reserved_engines`，不在 ids。不算接线」。其它行未改。

## 不做什么

不改 `catalog.json`、`qagent/src`、customer-shell、`run_tests.py`、`PROGRESS.md`。不把 pennylane 写进目录。不把 Cirq 说成 reserved。不接线。不 commit。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_l103_pl.py
PYTHONPATH=src python3 tests/test_iface_pl.py
```

`run_tests.py` 未改。
