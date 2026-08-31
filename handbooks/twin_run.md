# TwinRun 北向合同

算法侧只交这三个必填字段：

- `mode`
- `shots`
- `circuit.body`

不要交 CAL、shuttle、MS 矩阵。机器身份在服务端（`IONSTACK_TWIN_PRESET`）。

`GET /v1/twin/identity` 读孪生身份。`POST /v1/twin/run` 才签发 `twin_id`。

`ionstack_compile_estimate` 只有 `makespan_ns`，没有签收 `ok`。
Aer / IBM 的 `provenance` 不是 `qccd-twin`，禁止复制 `twin_id`。
