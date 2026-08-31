# H-04k · list_engines 点出 Pennylane reserved

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | S1 / H-04k |
| 范围 | `qagent/knowledge/manuals/list_engines.md` · `tests/test_h04k.py` |
| 未改 | `pennylane.md` · `eln.md` · 其它 manuals · `knowledge/README.md` · `adapters/docs.py` · `qagent/src/**` · `run_tests.py` · `PROGRESS.md` · `PARALLEL.md` · `test_h04e.py` · `test_h04j.py` |
| 层 | 第一层造包。检索仍走 `qccd_docs_search` / `WiredDocs`。不是第三套 loop |

## 结论

`QAGENT_KNOWLEDGE_PATH` 指到仓内 `qagent/knowledge` 时，`list_engines` / `哪些包` 仍必中 `manuals/list_engines.md`，`source=knowledge`，摘录 ≤400，`empty` 为假。手册全文 ≤400 字节。

在原有五包打头、Cirq interop、provenance 不是 qccd-twin、不要 CAL/shuttle 上，加一句：Pennylane 在 `reserved_engines`，不在目录。不算接线。不写「已接线」。不把 Cirq 写成 reserved。不接线 Pennylane。

## 语料

| 路径 | 放什么 |
|------|--------|
| `manuals/list_engines.md` | 哪些包 / 五包 / Cirq interop / Pennylane reserved_engines 不在目录 |

禁止：实验比特串、secrets、整段 QASM / Pauli、假例子 `twin_id`、手册出现 `twin_id=` / `twin_id:`、`import `、urllib / requests / httpx / socket、把 CAL / shuttle 当工具、把 Pennylane 写成已接线、把 Cirq 写成 reserved。

## 测

```bash
cd /Users/shl/nvidia/qagent && PYTHONPATH=src python3 tests/test_h04k.py
cd /Users/shl/nvidia/qagent && PYTHONPATH=src python3 tests/test_h04e.py
cd /Users/shl/nvidia/qagent && PYTHONPATH=src python3 tests/test_h04j.py
```

## 不做

- 不改 `qagent/src/**`。不改 `docs.py` 摘录合同。
- 不改 `pennylane.md`。不新建手册。
- 不接线 Pennylane。不算接线。
- 不新写 agent loop。不调 `ionstack_twin_run`。
- 不铸 `twin_id`。
- 不 commit。`run_tests.py` / `PROGRESS.md` 留给调度挂测。
