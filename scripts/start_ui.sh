#!/usr/bin/env bash
# Human entry is the Qagent agent chat + workplace settings. dsh is the full runtime.
set -euo pipefail
QAGENT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${QAGENT_ROOT}"
export PYTHONPATH=src
export QAGENT_PRESET="${QAGENT_PRESET:-lab}"
# H-03h: 空 HOME / 包 URL 从 dsh.env 再从 workplace.json 补 export。环境里已有非空值不覆盖。
# 永不读 secrets.json。永不 export QAGENT_CLOUD_URL / 密钥。空 URL 不是 localhost。
_dsh_env="${QAGENT_ROOT}/.qagent/dsh.env"
if [[ -f "${_dsh_env}" ]]; then
  while IFS= read -r _home_line || [[ -n "${_home_line}" ]]; do
    case "${_home_line}" in
      QAGENT_QDATA_HOME=*|QAGENT_QCHEM_HOME=*|QAGENT_IONSTACK_HOME=*|QAGENT_KNOWLEDGE_PATH=*|QAGENT_QDATA_URL=*|QAGENT_QCHEM_URL=*|QAGENT_TWIN_URL=*|QAGENT_ALGO_HUB_URL=*)
        _home_key="${_home_line%%=*}"
        if [[ -z "${!_home_key:-}" ]]; then
          export "${_home_key}=${_home_line#*=}"
        fi
        ;;
    esac
  done < "${_dsh_env}"
fi
unset _dsh_env
_workplace_file="${QAGENT_WORKPLACE_FILE:-${QAGENT_ROOT}/.qagent/workplace.json}"
while IFS= read -r _home_line || [[ -n "${_home_line}" ]]; do
  case "${_home_line}" in
    QAGENT_QDATA_HOME=*|QAGENT_QCHEM_HOME=*|QAGENT_IONSTACK_HOME=*|QAGENT_KNOWLEDGE_PATH=*|QAGENT_QDATA_URL=*|QAGENT_QCHEM_URL=*|QAGENT_TWIN_URL=*|QAGENT_ALGO_HUB_URL=*)
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
    ("qchem_home", "QAGENT_QCHEM_HOME"),
    ("ionstack_home", "QAGENT_IONSTACK_HOME"),
    ("knowledge_path", "QAGENT_KNOWLEDGE_PATH"),
    ("qdata_url", "QAGENT_QDATA_URL"),
    ("qchem_url", "QAGENT_QCHEM_URL"),
    ("twin_url", "QAGENT_TWIN_URL"),
    ("hub_url", "QAGENT_ALGO_HUB_URL"),
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
unset _workplace_file _home_line _home_key
PORT="${QAGENT_UI_PORT:-3080}"
if ! python3 -c '
import socket
import sys

sock = socket.socket()
sock.settimeout(0.4)
code = 0
try:
    sock.connect(("127.0.0.1", int(sys.argv[1])))
    code = 1
except OSError:
    code = 0
finally:
    sock.close()
raise SystemExit(code)
' "${PORT}"; then
  echo "port ${PORT} is already in use. Stop the old dsh-web or set QAGENT_UI_PORT." >&2
  exit 1
fi
if [[ -z "${QAGENT_SHELL_TOKEN:-}" ]]; then
  QAGENT_SHELL_TOKEN="$(python3 -c 'import secrets; print(secrets.token_hex(16))')"
  export QAGENT_SHELL_TOKEN
fi
echo "Qagent http://127.0.0.1:${PORT}/?token=${QAGENT_SHELL_TOKEN}"
echo "客户脸 http://127.0.0.1:${PORT}/?token=${QAGENT_SHELL_TOKEN}&role=customer"
echo "客户租户示例 http://127.0.0.1:${PORT}/?tenant=cust-a&token=${QAGENT_SHELL_TOKEN}&role=customer"
exec python3 -m qagent.entrypoints.shell_cli --serve --host 127.0.0.1 --port "${PORT}"
