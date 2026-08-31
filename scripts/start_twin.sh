#!/usr/bin/env bash
set -euo pipefail
QAGENT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# A-03f: 空 IONSTACK HOME 从 dsh.env / workplace.json 补。环境里已有非空值不覆盖。
# 只认 ionstack_home。永不读 secrets.json。永不 export QAGENT_CLOUD_URL / 密钥。
# 不算接线。不算活 Twin 已通。不铸 twin_id。
if [[ -z "${QAGENT_IONSTACK_HOME:-}" && -f "${QAGENT_ROOT}/.qagent/dsh.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${QAGENT_ROOT}/.qagent/dsh.env"
  set +a
fi
_workplace_file="${QAGENT_WORKPLACE_FILE:-${QAGENT_ROOT}/.qagent/workplace.json}"
while IFS= read -r _home_line || [[ -n "${_home_line}" ]]; do
  case "${_home_line}" in
    QAGENT_IONSTACK_HOME=*)
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
    ("ionstack_home", "QAGENT_IONSTACK_HOME"),
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
IONSTACK_HOME="${QAGENT_IONSTACK_HOME:-}"
if [[ -z "${IONSTACK_HOME}" ]]; then
  echo "set QAGENT_IONSTACK_HOME to the ionstack checkout" >&2
  exit 1
fi
export IONSTACK_TWIN_PRESET="${IONSTACK_TWIN_PRESET:-t_junction}"
export QAGENT_TWIN_URL="${QAGENT_TWIN_URL:-http://127.0.0.1:8765}"
exec "${IONSTACK_HOME}/.venv/bin/ionstack-serve" --host 127.0.0.1 --port 8765
