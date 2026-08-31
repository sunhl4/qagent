from __future__ import annotations

import argparse
import json

from qagent.adapters.preset import PRESETS, active_preset
from qagent.services.invoke import invoke

_TOOLS = (
    "qagent_list_engines",
    "qdata_run_recipe",
    "qdata_dequant_gate",
    "qchem_run",
    "qagent_pin_circuit",
    "qiskit_aer_run",
    "ionstack_compile_estimate",
    "ionstack_twin_run",
    "qccd_docs_search",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qagent-shell")
    parser.add_argument("--tool", help="same northbound tool name as dsh")
    parser.add_argument("--preset", default=active_preset())
    parser.add_argument("--args", default="{}")
    parser.add_argument("--approved", action="store_true")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3080)
    parser.add_argument("--eval", action="store_true")
    ns = parser.parse_args(argv)
    if ns.serve:
        from qagent.entrypoints.shell_http import serve

        serve(ns.host, ns.port)
        return 0
    if ns.eval:
        from qagent.services.eval_run import DEFAULT_EVAL_IDS, run_evals

        rows = run_evals(*DEFAULT_EVAL_IDS)
        print(json.dumps([{"id": r.id, "ok": r.ok, "detail": r.detail} for r in rows], indent=2))
        return 0 if all(r.ok for r in rows) else 1
    if ns.list or not ns.tool:
        print(json.dumps({"tools": list(_TOOLS), "presets": list(PRESETS), "active_preset": active_preset()}))
        return 0
    args = json.loads(ns.args)
    result = invoke(ns.tool, ns.preset, args, approved=ns.approved)
    print(json.dumps(result.__dict__, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
