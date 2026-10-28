#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"
# First bootstrap uses pip-tools 7.5.3; subsequent runs install the existing hash lock first.
export CUSTOM_COMPILE_COMMAND="bash scripts/lock_python.sh"
python -m piptools compile --generate-hashes --allow-unsafe --resolver=backtracking \
  --strip-extras --no-emit-index-url --no-emit-trusted-host \
  --output-file=runtime/python-dev.lock runtime/python-dev.in "$@"
