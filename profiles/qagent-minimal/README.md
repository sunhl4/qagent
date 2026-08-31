# profile `qagent-minimal`

两阶段第一段：只组合政策、引擎目录、手册、品牌。产物里没有 Twin / qdata / qchem / Aer / Codex。

```bash
# 对齐硬规与三句柄之后，再切全量
dsh --profile qagent-minimal
dsh --profile qagent
```

preset 用 `boot`：`echo boot > .qagent/active_preset`。全量实验室仍是 `dsh --profile qagent` + `lab`。
