#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=src
export QAGENT_TWIN_URL="${QAGENT_TWIN_URL:-http://127.0.0.1:8765}"
python3 -m qagent.entrypoints.eval_cli
python3 -m qagent.entrypoints.shell_cli --eval >/tmp/qagent-shell-eval.json
echo "shell-eval wrote /tmp/qagent-shell-eval.json"
