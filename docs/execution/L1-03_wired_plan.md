# L1-03 · Cirq reserved→wired 之前必须放松的断言

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | S2 / L1-03-plan |
| 范围 | 只写接线前必须放松的测试锁。不改 catalog、不改五包断言、不接线 |
| 层 | Layer 1 造包。不是客户 Agent，不是第三套 loop |
| 状态 | **计划**。Cirq 仍 reserved。本笔记**不标** L1-03 wired |

## 当前冻结（不是接线后）

`list_engines()` 冻成恰好五包：`qdata` / `qchem` / `ionstack` / `route` / `qiskit`。`load_engine_packs()` 只读 `catalog.engines[]`，不读 `reserved_engines`。

Cirq 在 `reserved_engines`，**不在** `engines[]`。`list_engines()` / `qagent_list_engines` 的 `engines[]` 因此不含 `cirq`。

E22 已存在，且 `status=empty`（`cirq_simulator_run` deny，载荷无第三句柄）。不要加 E23。不要加 Q-c06（产品评测 `Q-c` 仍是 Q-c01–Q-c05）。

本笔记**拒绝**把「Cirq 已接线」「engines 已含 cirq」写成当前状态。那两句不是现状。Cirq stays reserved until those are relaxed.

## 接线前必须放松（文件 + 精确断言）

把 `reserved_engines.cirq` 拷进 `engines[]` **之前**，调度必须先放松下列锁。本流不改这些文件，也不改五包断言。Cirq 保持 reserved，直到这些断言被放松。

### `qagent/tests/test_engines.py`（恰好五 id）

`test_five_packs`：

```python
assert [e.id for e in list_engines()] == ["qdata", "qchem", "ionstack", "route", "qiskit"]
```

同一五 id 还冻在 `run_tests.py` `test_engines()`（本流不许改 `run_tests.py`）。

### `qagent/tests/test_a05.py` / `company_shell` / L1-03 reserved

`test_a05.py` `_CANONICAL_PACKS = ("qdata", "qchem", "ionstack", "route", "qiskit")`。

`test_invoke_list_assets_and_engines`：

```python
assert pack_ids == list(_CANONICAL_PACKS)
```

`test_engines_reserved_stay_reserved`：

```python
assert [pack.id for pack in packs] == list(_CANONICAL_PACKS)
assert ids == list(_CANONICAL_PACKS)
assert "cirq" not in ids
```

以及 `assert all(pack.status == STATUS_WIRED for pack in packs)`。Cirq 若进 `list_engines()` 且仍 `reserved`，或六包却仍比五 id，都会红。

`run_tests.py` `test_company_shell`（company_shell）：

```python
assert [e["id"] for e in payload["engines"]] == ["qdata", "qchem", "ionstack", "route", "qiskit"]
```

`qagent/tests/test_l103.py`（L1-03 reserved asserts）——本流不改：

```python
assert listed == list(_FIVE)
assert "cirq" not in listed
reserved = [row for row in raw.get("reserved_engines") or [] if row.get("id") == "cirq"]
assert reserved, "cirq pack missing from catalog reserved_engines"
assert pack["status"] == "reserved"
```

以及 port / method：`assert cirq["status"] == "reserved"`、`assert row.status == "reserved"`；`cirq_*` `decide`/`invoke` 仍 deny。接线流要先改这些 reserved 断言，不能假装 L1-03 已经 wired。

### `test_ports` · `run_evals` still E01–E21

`qagent/tests/run_tests.py` `test_ports()` 仍只跑 E01–E21：

```python
for row in run_evals(*[f"E{i:02d}" for i in range(1, 22)]):
    assert row.ok, f"{row.id}: {row.detail}"
```

`qagent/tests/test_ports.py` 本身没有 `run_evals`；活门在 `run_tests.py` `test_ports`。`qagent/tests/test_eval.py` 同样是 `run_evals(*[f"E{i:02d}" for i in range(1, 22)])` 且 `len(results) == 21`。`test_contracts.py` 仍写 `ids == [f"E{i:02d}" for i in range(1, 22)]`（恰好 E01–E21）。E22 empty 已在树里，但不进上述 E01–E21 集合。不要加 E23。

## 接线后仍冻（本计划不实施）

调度以后若把 Cirq 推进 `engines[]`：

- `packages/qagent-cirq` 的 `execute` **仍只** `invoke()`（`registerInvokeTool`）。不要直连 Cirq 核。
- 句柄仍只有 `circuit_id` / `asset_id` / `twin_id`。不要第四个句柄。
- 不要假 `twin_id`。只有 ionstack TwinRun 能发。Cirq 模拟器 provenance 合同是 `cirq`，不是 `qccd-twin`。
- `qagent/src` 仍禁止 `import cirq`。未接线禁止 import 该核；本计划也不在 `qagent/src` 写 Cirq。
- 不要加 E23。不要加 Q-c06。

## 本流不做

- 不把 Cirq 写进 `engines[]`。不改 `catalog.json` / `engines.py` / 五包断言。
- 不改 `test_engines.py`、`test_a05.py`、`test_l103.py`、`test_ports.py`、`test_contracts.py`、`run_tests.py`、`PROGRESS.md`、`qagent/src/**`。
- 不铸 `twin_id`。不 commit。不标 L1-03 wired。
