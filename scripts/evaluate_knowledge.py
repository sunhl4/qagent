#!/usr/bin/env python3
"""Evaluate explicitly supplied deidentified retrieval cases without model calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from company_agent import knowledge  # noqa: E402
from company_agent.catalog import current_contract_digest  # noqa: E402
from company_agent.jsonutil import loads  # noqa: E402


def evaluate(corpus: Path, cases: Path) -> dict:
    """Report rankings and coverage, keeping source text and questions out of reports."""
    if not corpus.is_absolute() or corpus.is_symlink() or not corpus.is_dir():
        raise ValueError("corpus must be an explicit absolute nonsymlink directory")
    if cases.is_symlink() or not cases.is_file() or cases.stat().st_size > 1_000_000:
        raise ValueError("cases must be a bounded regular file")
    raw = cases.read_bytes()
    spec = loads(raw.decode("utf-8"))
    if not isinstance(spec, dict) or set(spec) != {"version", "scope", "cases"}:
        raise ValueError("invalid evaluation specification")
    if spec["version"] != "1.0" or spec["scope"] not in {"synthetic", "operator_deidentified"}:
        raise ValueError("invalid evaluation scope")
    if not isinstance(spec["cases"], list) or not 1 <= len(spec["cases"]) <= 1000:
        raise ValueError("evaluation must contain 1 to 1000 cases")
    ranks, recall, empty, coverage, latency = [], [], [], [], []
    identifiers = set()
    rows = []
    with patch.object(knowledge, "roots", lambda: (("builtin", corpus),)):
        for case in spec["cases"]:
            if not isinstance(case, dict) or set(case) != {"id", "query", "relevant"}:
                raise ValueError("invalid evaluation case")
            identity = case["id"]
            if (
                not isinstance(identity, str)
                or not identity.isascii()
                or not identity.isalnum()
                or len(identity) > 64
                or identity in identifiers
            ):
                raise ValueError("case identifiers must be unique bounded alphanumeric strings")
            identifiers.add(identity)
            relevant = case["relevant"]
            if (
                not isinstance(relevant, list)
                or len(relevant) > 32
                or any(not isinstance(item, str) for item in relevant)
            ):
                raise ValueError("relevant sources must be bounded relative paths")
            if len(set(relevant)) != len(relevant):
                raise ValueError("relevant sources must be unique")
            for item in relevant:
                path = Path(item)
                resolved = (corpus / path).resolve()
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or not resolved.is_relative_to(corpus.resolve())
                    or not resolved.is_file()
                ):
                    raise ValueError("relevant source is unavailable")
            start = time.perf_counter()
            found = knowledge.search({"query": case["query"]})
            latency.append((time.perf_counter() - start) * 1000)
            names = [hit["source"].split(":", 1)[1] for hit in found["hits"]]
            rank = next((index + 1 for index, name in enumerate(names) if name in relevant), 0)
            coverage.append(found["scan"]["complete"])
            if relevant:
                ranks.append(rank)
                recall.append(len(set(names) & set(relevant)) / len(relevant))
            else:
                empty.append(not names)
            rows.append(
                {
                    "id": identity,
                    "first_relevant_rank": rank,
                    "hits": len(names),
                    "scan_complete": found["scan"]["complete"],
                }
            )
    return {
        "version": "1.0",
        "scope": spec["scope"],
        "scientific_or_model_execution": False,
        "business_acceptance": "requires_operator_review"
        if spec["scope"] == "operator_deidentified"
        else "not_real_corpus",
        "contract_digest": current_contract_digest(),
        # Digest the input specification only. Corpus versions are supplied per
        # hit by the retrieval contract; this is not a full corpus attestation.
        "cases_sha256": hashlib.sha256(raw).hexdigest(),
        "case_count": len(rows),
        "complete_scans": all(coverage),
        "top1": statistics.mean(rank == 1 for rank in ranks) if ranks else None,
        "recall_at8": statistics.mean(recall) if recall else None,
        "mrr_at8": statistics.mean(1 / rank if rank else 0 for rank in ranks) if ranks else None,
        "empty_accuracy": statistics.mean(empty) if empty else None,
        "median_ms": round(statistics.median(latency), 3),
        "cases": rows,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = evaluate(args.corpus, args.cases)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
    except (OSError, ValueError, TypeError, RuntimeError):
        print("evaluation failed; verify explicit inputs and unused output path", file=sys.stderr)
        return 1
    return 0 if report["complete_scans"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
