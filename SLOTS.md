# 槽位索引

机器可读真源是 `contracts/slots.json`。全部 `implemented`。

## P0–P3

政策、引擎目录、pin、qdata 合同 store、Qiskit/Aer、ELN、Skills、TwinRun、qchem CLI、docs、沙箱、卡片、attended Codex、route 换后端、客户壳都已接线。

评测：`PYTHONPATH=src python -m qagent.entrypoints.eval_cli`（E01–E21、E28–E32；E22 仍 empty；E23 留给 Pennylane 锁）。

G-01 治理槽：`S-GOV-01` … `S-GOV-10` 已接线。G-02 可诊断性：`S-UX-01`（`contracts/errors.json`）。
