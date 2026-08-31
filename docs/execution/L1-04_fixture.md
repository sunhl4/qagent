# L1-04 · 算法验收夹具（字段冻住；无单测 = fail）

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-26 |
| 角色 | Q / L1-04 |
| 层 | Layer 1 造包。不是客户 Agent，不是第三套 loop |

## 结论

五包（qdata / qchem / ionstack / route / qiskit）的**输入/输出字段名**冻在 `qagent/tests/fixtures/benchmark_v1.json`。夹具只认句柄与诚实键，不跑 live CLI / Twin。Cirq reserved，不在 `list_engines()`，**不要求**夹具 case。

`missing_pack_tests(test_root)`：`list_engines()` 里的包，缺夹具 case **或**没有任何 `test_*.py` 点到该 pack id，就列出来。「不像就不算过」——无单测 = fail。当前五包两边都有，返回空。

# 禁止 twin_id 作为 required output

任何 fixture case 不得把第三句柄放进 `required_output_fields`。ionstack 代表工具是 `ionstack_twin_identity`（身份，不发句柄）。只有 TwinRun 能发该句柄；本夹具不调 TwinRun。

## 冻住的字段名（不是散文）

| 键 | 含义 |
|----|------|
| `version` / `cases` | 夹具顶层 |
| `pack_id` | 五包之一 |
| `invoke_tool` | 该包代表 invoke 名 |
| `required_input_fields` | 输入字段名 |
| `required_output_fields` | 输出字段名（句柄 / 诚实键） |
| `forbidden_output_fields` | 禁止出现的键 |
| `output_const` | 常量输出（Aer `provenance=aer`） |

产品里已经为真：

| pack_id | invoke_tool | required_output | 禁止 |
|---------|-------------|-----------------|------|
| qdata | `qdata_run_recipe` | `asset_id` | 第三句柄 |
| qchem | `qchem_run` | `asset_id` | 第三句柄 |
| ionstack | `ionstack_twin_identity` | `preset`, `live` | 第三句柄 |
| route | `ionstack_compile_estimate` | `makespan_ns` | `ok`、第三句柄 |
| qiskit | `qiskit_aer_run` | `provenance`（const `aer`） | 第三句柄 |

## 落盘

| 文件 | 作用 |
|------|------|
| `qagent/tests/fixtures/benchmark_v1.json` | 字段合同 |
| `qagent/src/qagent/services/benchmark.py` | `load_fixture()` + `missing_pack_tests()` |
| `qagent/tests/test_l104.py` | stdlib 门槛 |
| 本笔记 | 交卷 |

`qagent/src` 不 `import qdata` / `ionstack` / `qchem` / `qiskit` / `cirq`。未新增 agent loop。未改 `.github/workflows/qagent-eval.yml`（`test_q02b` 冻其命令）。CI 已跑 `tests/run_tests.py`；调度以后再挂 `test_l104`。`run_tests.py` 未改。

## 完成条件

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_l104.py
```

`test_l104.py` 退出 0。未 commit。

## 不做

- 不改 `run_tests.py`、`PROGRESS.md`、`qagent-eval.yml`、`test_q02b.py`、`eval_stub_provider.py`。
- 不改 `contracts/engines/catalog.json`、`contracts/eval/E*.json`、`contracts/eval/Q-*.json`。
- 不调 live qdata / qchem / Twin，不铸第三句柄。
- 不加 E23。Cirq 保持 reserved。
