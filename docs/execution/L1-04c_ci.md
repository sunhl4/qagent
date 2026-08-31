# L1-04c · 无单测门挂进 Q-02 同一 CI job

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | Q / L1-04c |
| 范围 | `.github/workflows/qagent-eval.yml` 加一步 · `qagent/scripts/check_missing_pack_tests.py` · `qagent/tests/test_l104c.py` |
| 层 | Layer 1 造包。不是客户 Agent，不是第三套 loop |
| 状态 | **Cirq 已接线**。已在 `list_engines()`。CI 跟目录走。不算 G3 |

## 做了什么

L1-04 已有 `missing_pack_tests()`（读 `benchmark_v1.json` + `list_engines()`）。本包把它挂进 **Q-02 同一门** `qagent-eval.yml`，不新开 job，不新开 loop。

仓根工作流仍是 `working-directory: qagent`，前两句不动：

```text
PYTHONPATH=src python3 tests/run_tests.py
PYTHONPATH=src python3 tests/run_qagent_vs_codex.py
```

第三步：`PYTHONPATH=src python3 scripts/check_missing_pack_tests.py`。内部是 `missing_pack_tests(Path("tests"))`；返回非空则退出 1（无单测 = CI 红）。`missing_pack_tests` 跟 `list_engines()`：目录里有谁，门就查谁。五包仍打头：qdata / qchem / ionstack / route / qiskit。Cirq 已接线，已在 `list_engines()`，因此 CI 也要求 Cirq 夹具 + 有单测提到它。helper 只调门槛函数，源码不写死包名。

不声明密钥，不上传 CI 产物，不 spawn 官方 Codex，不调 TwinRun，不铸 `twin_id`。夹具与门槛函数未改。

本步是 L1 造包门，不是 G3 过门，也不代替 G0–G4 正式演示。不算 G3。

## 测

```text
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_q02b.py
PYTHONPATH=src python3 tests/test_l104.py
PYTHONPATH=src python3 tests/test_l104c.py
PYTHONPATH=src python3 tests/test_l104c_align.py
```

`test_q02b.py` 仍认两句原命令。`test_l104c.py` 认第三步、本注记、无密钥 / 无官方 Codex 调用。`test_l104c_align.py` 认本注记已对齐接线。`run_tests.py` 未改；调度回收时再挂本测。

## 不做

- 不改 `run_tests.py`、`PROGRESS.md`、`test_q02b.py`、`test_l104.py`、`qagent/src/**`。
- 不加官方 Codex、密钥、TwinRun 到 CI。
- 不发明第四个句柄。不 commit。
