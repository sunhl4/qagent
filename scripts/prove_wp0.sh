#!/usr/bin/env bash
set -euo pipefail

QAGENT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export DSH_HOME="${QAGENT_ROOT}/.dsh-home"
DSH_BIN="${QAGENT_ROOT}/.dsh-runtime/node_modules/.bin/dsh"
PORT="${QAGENT_DSH_PORT:-3081}"

if [[ ! -x "${DSH_BIN}" ]]; then
  echo "dsh missing; run scripts/bootstrap_wp0.sh first" >&2
  exit 1
fi

DUMP="${QAGENT_ROOT}/.dsh-runtime/qagent-dsh-dump.yml"
"${DSH_BIN}" --profile qagent --dump-config >"${DUMP}"
echo "dump-config ok"

for id in qagent-policy qagent-engines qagent-qdata qagent-twin qagent-qchem qagent-qiskit qagent-brand; do
  grep -q "id: ${id}" "${DUMP}" || { echo "missing ${id} in dump-config" >&2; exit 1; }
done
grep -q "permissionMode: never" "${DUMP}" || { echo "Codex permissionMode missing" >&2; exit 1; }
grep -q "fetch: false" "${DUMP}" || { echo "tool-web fetch not off" >&2; exit 1; }
if grep -q "id: tool-cordis" "${DUMP}"; then
  echo "tool-cordis must not be in the qagent tree" >&2
  exit 1
fi
echo "qagent overlay ok"

exec "${DSH_BIN}" --profile qagent --host 127.0.0.1 --port "${PORT}" --no-open
