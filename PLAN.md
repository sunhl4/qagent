# 执行入口

顺序、门禁、演示在：

**[docs/qagent_design_plan.md](../docs/qagent_design_plan.md)**

WP0–WP10 已做完。qdata-mcp 已按计划硬化（`data_dir` / allowlist / 截断 get_job / B3）。ionstack / qchem 仍只走 REST 与 CLI。接口见 [INTERFACES.md](INTERFACES.md)。

```bash
PYTHONPATH=src python tests/run_tests.py
PYTHONPATH=src python -m qagent.entrypoints.eval_cli
bash scripts/ci_eval.sh
```

`invoke("qdata_run_recipe", "lab", {"name": "a2_chem_pes"})` → `ok` + `asset_id`。  
`invoke("ionstack_twin_run", …)` 未批准 → `needs_ask`。

治理包（G-01）：`boot` preset、`qagent-minimal`、后验证人、`qagent-doctor`、handoff v1、E28–E32。见 [docs/execution/G-01_gov.md](../docs/execution/G-01_gov.md)。
