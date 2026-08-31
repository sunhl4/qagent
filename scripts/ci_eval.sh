#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=src
python3 tests/run_tests.py
python3 -m qagent.entrypoints.eval_cli
