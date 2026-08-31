# L1-01d · 夹具 ProblemProvider 演练

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-26 |
| 角色 | P / algo |
| Skill | `qagent/skills/write-provider/SKILL.md` |
| 层 | Layer 1 造包。不是客户 Agent |

## 结论

按 write-provider Skill 加了一个**测试夹具** `ProblemProvider`，单测绿。未改 `qagent/src`，未登记引擎，未调 TwinRun。

# 禁止 twin_id

## 落盘（夹具，不是包）

`.qagent/` 在 `qagent/.gitignore` 里，所以夹具不写 `spi_scratch`，写可入库路径：

| 文件 | 作用 |
|------|------|
| `qagent/tests/fixtures/eval_stub_provider.py` | `name = eval_stub` + `describe()` |
| `qagent/tests/test_l101d.py` | import 夹具；`name` 在；第三句柄属性不在 |
| 本笔记 | 交卷 |

名字 `eval_stub`：`snake_case`，不含 cal / shuttle / twin。

句柄只认 `circuit_id` / `asset_id`。本夹具不发句柄。

## 完成条件

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_l101d.py
PYTHONPATH=src python3 tests/run_tests.py
```

`test_l101d.py` 与 `run_tests.py` 均退出 0。`run_tests.py` 未改；调度回收时再挂本测。

本 diff：`ionstack` TwinRun 符号零命中；第三句柄字面量只出现在「禁止」注释。

## 不做

- 不改 `qagent/src/qagent/`（无 adapter / chat / ionstack）。
- 不 `import qdata` / `ionstack` / `qchem` / `qiskit`。
- 不注册 TwinRun，不给官方 Codex 看 Twin。
- 不改 `run_tests.py`、`PROGRESS.md`、customer-shell、contracts/eval、assignment、`qdata.py`。
- 不 commit。
