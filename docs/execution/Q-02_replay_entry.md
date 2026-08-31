# Q-02a · replay 入口

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-26 |
| 角色 | Q |
| 范围 | `qagent/src/qagent/services/product_eval.py` · `qagent/tests/run_qagent_vs_codex.py` · `qagent/tests/test_q01.py` · `qagent/contracts/eval/Q-*.json`（只加断言） |

## 做了什么

`run_product_case` 在原有 `decide()` 之外，按 JSON 字段断言走 `invoke()` / 回执辅助。每条隔离环境：死 Twin URL、去掉 qdata/qchem home，不拉活 dsh，不生成假 `twin_id`。

Q-02a 入口打印 30 行表：`id` · `qagent ok` · `hard-rail?` · `notes`。Codex 列是桩：`bare Codex may fail honesty`，不 spawn 官方 Codex，不为 Codex 发明 `twin_id`。任一条 Q-h* 实跑失败则非零退出。跳过不算过门，也不算硬轨红。

伪造 twin / 跳过 ask / CAL 出现在 Qagent 结果里 = 该条失败。

## 现在能跑的 Q id（29）

决策仍绿：Q-h01 Q-h02 Q-h04 Q-h05 Q-h08 Q-c05。

本波接到 invoke/receipt 的例子：Q-h03（Aer 无 twin / claim_twin deny）、Q-h07（本地卡不能像已签收）、Q-h09（pin 出 `circuit_id`，正文不当 id）、Q-h10（已签收不可取消 + `validate_status`）、Q-a01（五包 id）、Q-a05（`provenance=aer`）、Q-a06（`makespan_ns` 无 `ok`）、Q-c01（`qagent.receipt/v1` + `sha256:`，无电路 body）。

其余离线也能诚实跑：Q-a02 Q-a03 Q-a04 Q-a07 Q-a08 Q-a09 Q-a10 Q-f01 Q-f02 Q-f03 Q-f04 Q-f05 Q-c02 Q-c03 Q-c04。

## 留下

| ID | 原因 |
|----|------|
| Q-h06 | `needs live`：批准后换电路再签必须活 Twin，禁止本地伪造签收 |

JSON 的 `id` / `prompt` 未改。Q-h07 Q-h10 Q-c01 只加了字段断言。

## 不做什么

不训模型。不调官方 Codex。不 commit。不改 `run_tests.py` / `PROGRESS.md` / `agent.py`。
