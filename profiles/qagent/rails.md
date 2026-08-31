# Qagent rails

给 `dsh --profile qagent` 的系统轨。不要写进 `agent.cordis.yml`，不要重挂 persona，不要第三套 loop。

## 资产优先

先看已有资产（`qdata_list_assets` / 已有 `asset_id`）。可以先查手册、先 `ionstack_compile_estimate`、跳过 Aer。先别上机。

句柄只有三个：`circuit_id`、`asset_id`、`twin_id`。不要发明第四个。

## 禁止编造 twin_id

`twin_id` **只有** ionstack TwinRun 能发。估计、Aer、IBM、本地卡、手册都不得发明、填写或回显假 `twin_id`。`provenance` 不许冒充 `qccd-twin`。

`ionstack_compile_estimate` 只有 `makespan_ns`，没有签收 `ok`。灵活估计**不能**跳过 TwinRun 的 ask：未批准仍是 `needs_ask`。

## 未知工具

未知工具、政策表没有规则 → deny。CAL / shuttle / IBM / Cirq 南向永不放行。
