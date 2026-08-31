# Qagent minimal rails

给 `dsh --profile qagent-minimal` 的系统轨。不要写进 `agent.cordis.yml`，不要第三套 loop。

句柄只有三个：`circuit_id`、`asset_id`、`twin_id`。这个 profile 的产物里没有 Twin 插件，因此也发不出 `twin_id`。

未知工具、政策表没有规则 → deny。CAL / shuttle 永不放行。
