# ELN / eln

ELN 只读 GET /api/eln，回 events。没有 POST 追加。无密钥、无电路正文。

五类事件：recipe_pin / estimate / twin_signoff / b3 / assignment。

另有 claim_blocked，短 reason 可见（Cirq 拒铸 cirq_claim_twin_id）。

fork 丢掉 twin_id。只有 TwinRun 能发 twin_id。本页不写假例子 id。

不要把 CAL 或 shuttle 当成工具。
