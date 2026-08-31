# L1-03 · 接线前放松「恰好五包」断言

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | S2 / L1-03-relax |
| 范围 | 只放松 `list_engines()`「恰好五 id」测试锁。不改 catalog、不接线 |
| 层 | Layer 1 造包。不是客户 Agent，不是第三套 loop |
| 状态 | **只放松断言**。Cirq 仍 reserved。本笔记**不算** Cirq 已接线，**不标** L1-03 wired |

## 当前冻结（不是接线后）

`list_engines()` 仍只读 `catalog.engines[]`。五包 `qdata` / `qchem` / `ionstack` / `route` / `qiskit` **必须仍在**，且仍打头。列表以后可以更长；测试不再写 `==` 恰好这五个 id。

Cirq 在 `reserved_engines`，**不在** `engines[]`。本笔记**拒绝**把「Cirq 已接线」「engines 已含 cirq」写成当前状态。那两句不是现状。Cirq stays reserved until a later wire step copies the reserved row.

E22 仍 `status=empty`。不要加 E23。不要加 Q-c06。不要铸 `twin_id`。`qagent/src` 仍禁止 `import cirq`。

## 改了哪些断言

### `qagent/tests/test_engines.py` `test_five_packs`

原先：`[e.id for e in list_engines()] ==` 恰好五 id。

现在：`ids[:5] == FIVE` 且 `set(FIVE) <= set(ids)`。五包打头；尾部可以再长。

调度回收时已放宽 `run_tests.py` `test_engines()` / `test_company_shell`：改为 `ids[:5] ==` 五包且五包都在。仍**不算** Cirq 已接线。`test_invoke.py` / `test_c03.py` / `test_l104.py` 里还有恰好五条，接线前还要再放。

### `qagent/tests/test_a05.py`

`_CANONICAL_PACKS` 五包仍必须出现。

`test_invoke_list_assets_and_engines`：`pack_ids ==` 改为 `pack_ids[:5] ==` 且集合包含五包。

`test_engines_reserved_stay_reserved`：去掉 `ids ==` 恰好五包，去掉无条件 `cirq not in ids`。改为五包打头且都在。`cirq not in ids` 仅当当前 listed 不含 cirq 时成立，不再锁死「永远不含 / 只能这五包」。五包本身仍要求 `wired`。`pennylane` / `uqc-hardware` 仍不在 listed。

### `qagent/tests/test_l103.py` `test_pack_exists_reserved`

原先：`listed ==` 恰好五条，且 `cirq not in listed`（接线后必红）。

现在：五包打头；**若** listed 里还没有 cirq，则 `reserved_engines` 必须有 cirq，且该行仍 `status=reserved`。不要读成「cirq 已经在 engines」。

port 仍 reserved，`cirq_*` 仍 deny。未改 catalog / `engines.py` / `qagent/src`。

## 本流不做

- 不把 Cirq 写进 `engines[]`。不改 `catalog.json` / `engines.py` / ports / `qagent/src/**`。
- 不改 `run_tests.py`、`PROGRESS.md`、customer-shell。
- 拒绝宣称 L1-03 已接线 / Cirq wired / engines 已含 cirq。那两句不是现状。
- 不铸 `twin_id`。不 commit。不 `import cirq`。
