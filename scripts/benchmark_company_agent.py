#!/usr/bin/env python3
"""Reproducible synthetic retrieval quality and local/loopback latency measurements."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from company_agent import catalog, knowledge  # noqa: E402
from company_agent.invoke import _invoke, invoke  # noqa: E402


def measure(function, repeats):
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        function()
        samples.append((time.perf_counter() - start) * 1000)
    ordered = sorted(samples)
    return {
        "samples_ms": [round(sample, 6) for sample in samples],
        "median_ms": round(statistics.median(samples), 3),
        "p95_ms": round(ordered[math.ceil(len(ordered) * 0.95) - 1], 3),
        "p95_method": "nearest_rank",
    }


def retrieval_evaluation():
    fixture = json.loads((ROOT / "tests/fixtures/knowledge_cases.json").read_text())
    result = {}
    with tempfile.TemporaryDirectory(prefix="company-knowledge-benchmark-") as temporary:
        root = Path(temporary)
        for name, content in fixture["documents"].items():
            (root / name).write_text(content, encoding="utf-8")
        original_terms = knowledge.query_terms
        for name, tokenizer in (
            ("whitespace", lambda q: tuple(dict.fromkeys(q.casefold().split()))),
            ("cjk_bigrams", original_terms),
        ):
            recall, reciprocal, empty_correct, latencies = [], [], [], []
            with (
                patch.object(knowledge, "roots", lambda: (("builtin", root),)),
                patch.object(knowledge, "query_terms", tokenizer),
            ):
                for case in fixture["cases"]:
                    start = time.perf_counter()
                    found = knowledge.search({"query": case["query"]})["hits"]
                    latencies.append((time.perf_counter() - start) * 1000)
                    names = [hit["source"].split(":", 1)[1] for hit in found]
                    if case["relevant"]:
                        recall.append(len(set(names) & set(case["relevant"])) / len(case["relevant"]))
                        reciprocal.append(
                            next(
                                (
                                    1 / (index + 1)
                                    for index, hit in enumerate(names)
                                    if hit in case["relevant"]
                                ),
                                0,
                            )
                        )
                    else:
                        empty_correct.append(not names)
            result[name] = {
                "recall_at_8": round(statistics.mean(recall), 4),
                "mrr_at_8": round(statistics.mean(reciprocal), 4),
                "empty_accuracy": statistics.mean(empty_correct),
                "samples_ms": [round(sample, 6) for sample in latencies],
                "median_ms": round(statistics.median(latencies), 3),
            }
    return {"documents": len(fixture["documents"]), "cases": len(fixture["cases"]), "methods": result}


def benchmarks(repeats):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            raw = json.dumps(
                {
                    "protocol": "company-agent-provider/1.0",
                    "ok": True,
                    "provider": "uniqon",
                    "request_id": request["request_id"],
                    "result": {"asset_id": "asset_fixture", "summary": {"status": "completed"}},
                }
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(raw.encode())

        def log_message(self, *_args):
            pass

    def checked_call(function, *args):
        result = function(*args)
        if result.status != "ok":
            raise RuntimeError("benchmark invocation failed; latency is not a success sample")
        return result

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with (
                contextlib.redirect_stderr(io.StringIO()),
                patch.dict(
                    os.environ,
                    {
                        "COMPANY_QUANTUM_PLATFORM_INVOKE_URL": f"http://127.0.0.1:{server.server_port}/invoke",
                        "COMPANY_QUANTUM_PLATFORM_TOKEN": "synthetic-benchmark-credential-never-in-results",
                        "COMPANY_AGENT_CONTRACTS_DIR": str(ROOT / "contracts"),
                    },
                ),
            ):
                result = {
                    "python_startup": measure(
                        lambda: subprocess.run(
                            [sys.executable, "-P", "-c", "pass"], check=True, capture_output=True
                        ),
                        repeats,
                    ),
                    "tools_read_validate": measure(catalog.load_tools, repeats),
                    "local_per_read": measure(
                        lambda: checked_call(_invoke, "company_capabilities", "lab", {}), repeats
                    ),
                    "local_snapshot": measure(
                        lambda: checked_call(invoke, "company_capabilities", "lab", {}), repeats
                    ),
                    "loopback_provider": measure(
                        lambda: checked_call(
                            invoke,
                            "quantum_algorithm_run",
                            "lab",
                            {
                                "algorithm": "fixture",
                                "component_version": "1.0",
                                "catalog_version": "cat_fixture",
                            },
                        ),
                        repeats,
                    ),
                }
                runtime_root = Path(os.environ.get(
                    "COMPANY_AGENT_RUNTIME_DIR",
                    Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
                    / "unitqc-company-agent/dsh-runtime",
                ))
                node = runtime_root / "node_modules/node/bin/node"
                bridge_uri = (ROOT / "packages/company-agent-core/src/runtime.js").as_uri()
                bridge_env = {
                    "PATH": "/usr/bin:/bin", "COMPANY_AGENT_PROFILE": "company-agent",
                    "COMPANY_AGENT_PRESET": "lab",
                    # The CLI child runs bare; without this key it would charge
                    # the machine-wide default turn ledger instead of this
                    # run's throwaway key set in main().
                    "COMPANY_AGENT_TURN_ID": os.environ["COMPANY_AGENT_TURN_ID"],
                    "COMPANY_AGENT_PYTHON": sys.executable,
                    "COMPANY_AGENT_PYTHONPATH": str(ROOT / "src"),
                    "COMPANY_AGENT_CONTRACTS_DIR": str(ROOT / "contracts"),
                    "COMPANY_QUANTUM_PLATFORM_INVOKE_URL": f"http://127.0.0.1:{server.server_port}/invoke",
                    "COMPANY_QUANTUM_PLATFORM_TOKEN": "synthetic-benchmark-credential-never-in-results",
                }
                program = (
                    f"import {{invoke}} from {json.dumps(bridge_uri)};"
                    "const result=await invoke('quantum_algorithm_run',"
                    "{algorithm:'fixture',component_version:'1.0',catalog_version:'cat_fixture'});"
                    "if(result.status!=='ok')process.exit(1);"
                )
                result["node_bridge_cli_loopback_cold"] = measure(
                    lambda: subprocess.run(
                        [str(node), "--input-type=module", "-e", program],
                        env=bridge_env, check=True, capture_output=True, timeout=40,
                    ), repeats,
                )
        finally:
            server.shutdown()
            thread.join(timeout=3)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=10)
    args = parser.parse_args(argv)
    if not 1 <= args.repeats <= 100:
        parser.error("--repeats must be from 1 to 100")
    # The gate runs bare CLI calls; without an explicit turn key they would
    # charge the machine-wide default turn ledger and inherit ambient budget
    # state from every other shell/session (fail-closed once its invocation
    # limit trips). A fresh throwaway key keeps this run's receipts isolated,
    # same pattern as compliance_gate.py and test_bridge_behavior.py.
    os.environ["COMPANY_AGENT_TURN_ID"] = f"benchmark-{time.time_ns()}"
    quality = retrieval_evaluation()
    timings = benchmarks(args.repeats)
    print(
        json.dumps(
            {
                "version": "2.1",
                "scope": "synthetic_local_loopback_only",
                "quality": quality,
                "contract_digest": catalog.current_contract_digest(),
                "python": platform.python_version(),
                "system": platform.system(),
                "lock_sha256": hashlib.sha256((ROOT / "runtime/python-dev.lock").read_bytes()).hexdigest(),
                "repeats": args.repeats,
                "timings": timings,
            },
            ensure_ascii=False,
        )
    )
    methods = quality["methods"]
    return (
        0
        if (
            methods["cjk_bigrams"]["recall_at_8"] >= methods["whitespace"]["recall_at_8"]
            and methods["cjk_bigrams"]["mrr_at_8"] >= methods["whitespace"]["mrr_at_8"]
            and methods["cjk_bigrams"]["empty_accuracy"] == 1
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
