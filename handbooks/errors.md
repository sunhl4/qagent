# 错误目录

槽位号（S-TWIN-03、S-ENG-02、S-QISKIT-03）是填充位，不是原因。同一槽位可表示缺参、未就绪或拒收。

查错误走 `GET /api/errors?slot=S-TWIN-03` 或本手册。不要拿槽位号当健康灯。

## ESTIMATE_MISSING

预估缺 `circuit.body` 或钉住的线路没有 logical.body。先钉住线路，并带上 qasm3 / logical。qiskit 源不要只交 asset_id。

## ESTIMATE_UNREADY

预估通道没接通。看健康面的预估灯。孪生灯亮不等于预估可用。不要改用上机去试。

## ESTIMATE_REFUSED

这条线路预估拒了（南向键、签收字段、正文对不上句柄）。换线路或去掉禁键。

## PIN_MISSING

钉住线路：qiskit / qasm3 / logical / cirq 要 qasm3 或 logical；qchem / qdata 可交 asset_id。不要把缺参报成通用引擎故障。

## TWIN_UNREADY

TwinRun 没回签收句柄。不会本地伪造。看孪生灯。

## POLICY_DENY

当前预设不让这步。`qagent_list_engines` 不带 preset 是只读；带 preset 会切会话。

处置：看 `hint` 和健康四灯（孪生 / 预估 / 数据 / 待批）。预估失败是软信号，不硬性阻塞许可单。
