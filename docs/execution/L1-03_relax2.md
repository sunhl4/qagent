# L1-03 · 接线前放松余下「恰好五包」断言

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | S2 / L1-03-relax2 |
| 范围 | 只放松 `test_invoke.py` / `test_c03.py` / `test_l104.py` 余下的「恰好五 id」锁。不改 catalog、不接线 |
| 层 | Layer 1 造包。不是客户 Agent，不是第三套 loop |
| 状态 | **只放松余锁**。Cirq 仍 reserved。本笔记**不算** Cirq 已接线，**不标** L1-03 wired |

## 当前冻结（不是接线后）

`list_engines()` 仍只读 `catalog.engines[]`。五包 `qdata` / `qchem` / `ionstack` / `route` / `qiskit` **必须仍在**，且仍打头。列表以后可以更长；这三份测试不再写 `==` 恰好这五个 id。

Cirq 在 `reserved_engines`，**不在** `engines[]`。本笔记**拒绝**把「Cirq 已接线」「engines 已含 cirq」写成当前状态。那两句不是现状。不要读成 cirq 已经在 engines。Cirq stays reserved until a later wire step copies the reserved row.

E22 仍 `status=empty`。不要加 E23。不要加 Q-c06。不要铸 `twin_id`。`qagent/src` 仍禁止 `import cirq`。

## 改了哪些断言

### `qagent/tests/test_invoke.py` `test_list_engines_is_native`

原先：`ids ==` 恰好五 id。

现在：`ids[:5] == FIVE` 且 `set(FIVE) <= set(ids)`。五包打头；尾部可以再长。

### `qagent/tests/test_c03.py` `test_five_pack_unchanged`

原先：`ids ==` 恰好五 id，且无条件 `cirq not in ids`（接线后必红）。

现在：五包打头且都在。Cirq 现在仍不在 listed，但不再锁死「永远不含 / 只能这五包」。

### `qagent/tests/test_l104.py`

`test_fixture_parses_and_covers_wired`：原先 `wired ==` 恰好五条，且无条件 `cirq not in wired` / `cirq not in by_pack`。

现在：五包打头且都在；五包都有夹具。**若** listed 里还没有 cirq，则夹具也不要求 cirq。不要读成 cirq 已经在 engines。**现在** Cirq 仍不在 listed，当前树仍不必有 cirq 夹具。

`test_cirq_not_required`：原先无条件 `cirq not in ids`（永远不含）。现在：五包都有夹具；若 listed 还没有 cirq，则夹具也不要求 cirq。

未改 fixture JSON。未改 catalog / `engines.py` / `qagent/src`。

## 本流不做

- 不把 Cirq 写进 `engines[]`。不改 `catalog.json` / `engines.py` / ports / `qagent/src/**`。
- 不改 `run_tests.py`、`PROGRESS.md`、customer-shell、`test_engines.py`、`test_a05.py`、`test_l103.py`。
- 拒绝宣称 L1-03 已接线 / Cirq wired / engines 已含 cirq。那两句不是现状。
- 不铸 `twin_id`。不 commit。不 `import cirq`。
