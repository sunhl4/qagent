#!/usr/bin/env bash
# Live qdata HTTP. Requires QAGENT_QDATA_HOME. Does not import the qdata package.
set -euo pipefail
QAGENT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# A-01e: 空 HOME 从 dsh.env / workplace.json 补 export。环境里已有非空值不覆盖。
# 只认 qdata_home。永不读 secrets.json。永不 export QAGENT_CLOUD_URL / 密钥。
if [[ -z "${QAGENT_QDATA_HOME:-}" && -f "${QAGENT_ROOT}/.qagent/dsh.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${QAGENT_ROOT}/.qagent/dsh.env"
  set +a
fi
_workplace_file="${QAGENT_WORKPLACE_FILE:-${QAGENT_ROOT}/.qagent/workplace.json}"
while IFS= read -r _home_line || [[ -n "${_home_line}" ]]; do
  case "${_home_line}" in
    QAGENT_QDATA_HOME=*)
      export "${_home_line%%=*}=${_home_line#*=}"
      ;;
  esac
done < <(
  python3 - "${_workplace_file}" <<'HOMES'
import json
import os
import sys
from pathlib import Path

_MAP = (
    ("qdata_home", "QAGENT_QDATA_HOME"),
)

path = Path(sys.argv[1])
if not path.is_file():
    raise SystemExit(0)
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError, UnicodeError):
    raise SystemExit(0)
if not isinstance(data, dict):
    raise SystemExit(0)
for field, env_name in _MAP:
    if (os.environ.get(env_name) or "").strip():
        continue
    raw = data.get(field)
    if raw is None:
        continue
    value = str(raw).strip()
    if not value or "\n" in value or "\r" in value:
        continue
    print(f"{env_name}={value}")
HOMES
)
unset _workplace_file _home_line
QDATA_HOME="${QAGENT_QDATA_HOME:-}"
if [[ -z "${QDATA_HOME}" ]]; then
  echo "set QAGENT_QDATA_HOME to the qdata checkout" >&2
  exit 1
fi
QDATA_BIN="${QAGENT_QDATA_BIN:-${QDATA_HOME}/.venv/bin/qdata}"
if [[ ! -x "${QDATA_BIN}" ]]; then
  echo "qdata CLI missing at ${QDATA_BIN}" >&2
  exit 1
fi
export QAGENT_QDATA_URL="${QAGENT_QDATA_URL:-http://127.0.0.1:8787}"
DATA_DIR="${QAGENT_QDATA_SERVE_DIR:-${QAGENT_ROOT}/.qagent/qdata-serve}"
mkdir -p "${DATA_DIR}"
exec "${QDATA_BIN}" serve --host 127.0.0.1 --port 8787 --data-dir "${DATA_DIR}"
