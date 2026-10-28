#!/usr/bin/env bash
set -euo pipefail
umask 077
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# 私有开发配置（不进合同仓）：本机/内网服务的 token 等。显式环境变量优先，
# 文件缺失静默跳过；生产启动路径不受影响（生产凭据由受控注入）。
private_env="${COMPANY_AGENT_RUNTIME_ENV:-${XDG_CACHE_HOME:-${HOME}/.cache}/unitqc-company-agent/runtime-dev.env}"
if [[ -f "$private_env" ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    case "$line" in ''|\#*) continue ;; esac
    key="${line%%=*}"
    value="${line#*=}"
    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || { echo "invalid key in $private_env: $key" >&2; exit 2; }
    if [[ -z "${!key+x}" ]]; then export "$key=$value"; fi
  done < "$private_env"
fi
export DSH_HOME="${COMPANY_AGENT_DSH_HOME:-${XDG_CACHE_HOME:-${HOME}/.cache}/unitqc-company-agent/dsh-home}"
export COMPANY_AGENT_DEPLOYMENT_MODE="${COMPANY_AGENT_DEPLOYMENT_MODE:-development}"
PROFILE="${COMPANY_AGENT_PROFILE:-company-agent}"
if [[ "${PROFILE}" != "company-agent" && "${PROFILE}" != "company-agent-minimal" ]]; then
  echo "invalid COMPANY_AGENT_PROFILE=${PROFILE}" >&2
  exit 2
fi
export COMPANY_AGENT_PROFILE="${PROFILE}"
if [[ "${PROFILE}" == "company-agent-minimal" ]]; then
  if [[ "${COMPANY_AGENT_PRESET:-boot}" != "boot" && "${COMPANY_AGENT_PRESET:-boot}" != "algo" ]]; then
    echo "company-agent-minimal only supports boot or algo presets" >&2
    exit 2
  fi
  export COMPANY_AGENT_PRESET="${COMPANY_AGENT_PRESET:-boot}"
else
  export COMPANY_AGENT_PRESET="${COMPANY_AGENT_PRESET:-lab}"
fi
if [[ "${COMPANY_AGENT_PRESET}" != "boot" && "${COMPANY_AGENT_PRESET}" != "lab" && "${COMPANY_AGENT_PRESET}" != "algo" && "${COMPANY_AGENT_PRESET}" != "sign" ]]; then
  echo "invalid COMPANY_AGENT_PRESET=${COMPANY_AGENT_PRESET}" >&2
  exit 2
fi
RUNTIME="${COMPANY_AGENT_RUNTIME_DIR:-${XDG_CACHE_HOME:-${HOME}/.cache}/unitqc-company-agent/dsh-runtime}"
for path_value in "${DSH_HOME}" "${RUNTIME}"; do
  if [[ "${path_value}" != /* ]]; then
    echo "runtime paths must be absolute" >&2
    exit 2
  fi
done
if [[ -L "${DSH_HOME}" || -L "${RUNTIME}" ]]; then
  echo "runtime roots must not be symlinks" >&2
  exit 2
fi
if [[ "${COMPANY_AGENT_DEPLOYMENT_MODE:-development}" != "development" && "${COMPANY_AGENT_DEPLOYMENT_MODE:-development}" != "production" ]]; then
  echo "COMPANY_AGENT_DEPLOYMENT_MODE must be development or production" >&2
  exit 2
fi
DEPLOYMENT_MODE="${COMPANY_AGENT_DEPLOYMENT_MODE:-development}"
if [[ "${DEPLOYMENT_MODE}" == "production" ]]; then
  for required_name in COMPANY_AGENT_RELEASE_MANIFEST COMPANY_AGENT_RELEASE_ATTESTATION COMPANY_AGENT_RELEASE_TRUST_CONFIG; do
    if [[ -z "${!required_name:-}" || "${!required_name}" != /* ]]; then
      echo "production requires absolute ${required_name}" >&2
      exit 2
    fi
  done
  VERIFY_PYTHON="/usr/bin/python3"
  if [[ ! -x "${VERIFY_PYTHON}" ]]; then
    echo "production release verifier requires /usr/bin/python3" >&2
    exit 2
  fi
  unset PYTHONPATH PYTHONHOME PYTHONSTARTUP LD_PRELOAD LD_LIBRARY_PATH NODE_OPTIONS
  unset COMPANY_AGENT_ENABLE_CONFIGURED_KNOWLEDGE COMPANY_AGENT_KNOWLEDGE_PATH
  export COMPANY_AGENT_PYTHON="/usr/bin/python3"
  "${VERIFY_PYTHON}" -I "${ROOT}/scripts/release_manifest.py" verify \
    --manifest "${COMPANY_AGENT_RELEASE_MANIFEST}" \
    --root "${ROOT}" \
    --runtime-root "${RUNTIME}" \
    --require-immutable \
    --attestation "${COMPANY_AGENT_RELEASE_ATTESTATION}" \
    --trust-config "${COMPANY_AGENT_RELEASE_TRUST_CONFIG}" >&2
  managed_profile="${DSH_HOME}/profiles/${PROFILE}"
  if [[ ! -d "${managed_profile}" || "$(readlink -f "${managed_profile}")" != "${ROOT}/profiles/${PROFILE}" ]]; then
    echo "production DSH profile must resolve to the verified release profile" >&2
    exit 2
  fi
  export COMPANY_AGENT_PRODUCTION_VERIFIED=1
else
  unset COMPANY_AGENT_PRODUCTION_VERIFIED
  echo "Company Agent development launch: mutable workspace is not a production deployment" >&2
fi
DSH_ENTRY="${RUNTIME}/node_modules/@deepseek-ai/dsh/lib/bin.js"
NODE_BIN="${RUNTIME}/node_modules/node/bin/node"
if [[ ! -f "${DSH_ENTRY}" || ! -x "${NODE_BIN}" ]]; then
  echo "dsh runtime missing; run scripts/bootstrap_dsh.sh" >&2
  exit 1
fi
if [[ ! -d "${DSH_HOME}" ]]; then
  mkdir -p "${DSH_HOME}"
fi
chmod 700 "${DSH_HOME}"
preset_src="${ROOT}/profiles/${PROFILE}/agent-presets/company-agent"
presets_root="${DSH_HOME}/.agent-presets"
preset_dst="${presets_root}/company-agent"
rm -rf -- "${presets_root}"
mkdir -p "${preset_dst}"
cp -f "${preset_src}/agent.cordis.yml" "${preset_src}/preset.yml" "${preset_dst}/"
chmod 700 "${presets_root}" "${preset_dst}"
chmod 600 "${preset_dst}/agent.cordis.yml" "${preset_dst}/preset.yml"
skills_dst="${DSH_HOME}/skills"
rm -rf -- "${skills_dst}"
mkdir -p "${skills_dst}"
SYNC_PYTHON="${COMPANY_AGENT_PYTHON:-}"
if [[ -z "${SYNC_PYTHON}" || "${SYNC_PYTHON}" != /* ]]; then
  SYNC_PYTHON="$(command -v python3 || true)"
fi
if [[ -z "${SYNC_PYTHON}" || ! -x "${SYNC_PYTHON}" ]]; then
  echo "skill registry sync requires an executable python3" >&2
  exit 1
fi
# 技能挂载由 contracts/skills.json 准入注册表驱动：profile/preset 匹配的
# 未撤销条目才出现在运行时挂载根，摘要不匹配直接失败闭合。启动时未显式
# 选择 preset 时与运行时缺省一致（company-agent→lab、minimal→boot）。
SYNC_PRESET="${COMPANY_AGENT_PRESET:-}"
if [[ -z "${SYNC_PRESET}" ]]; then
  if [[ "${PROFILE}" == "company-agent-minimal" ]]; then
    SYNC_PRESET="boot"
  else
    SYNC_PRESET="lab"
  fi
fi
"${SYNC_PYTHON}" "${ROOT}/scripts/verify_skills.py" sync \
  --root "${skills_dst}" --profile "${PROFILE}" --preset "${SYNC_PRESET}" >/dev/null
"${SYNC_PYTHON}" "${ROOT}/scripts/verify_skills.py" verify \
  --root "${skills_dst}" --profile "${PROFILE}" --preset "${SYNC_PRESET}" >/dev/null
find "${skills_dst}" -type d -exec chmod 700 {} +
find "${skills_dst}" -type f -exec chmod 600 {} +
if [[ ! -f "${ROOT}/src/company_agent/__init__.py" ]]; then
  echo "company-agent Python package is missing" >&2
  exit 1
fi
COMPANY_AGENT_PYTHON="${COMPANY_AGENT_PYTHON:-$(command -v python3 || true)}"
if [[ -z "${COMPANY_AGENT_PYTHON}" || "${COMPANY_AGENT_PYTHON}" != /* || ! -x "${COMPANY_AGENT_PYTHON}" ]]; then
  echo "COMPANY_AGENT_PYTHON must be an absolute executable path" >&2
  exit 1
fi
unset COMPANY_AGENT_APPROVAL_CONTEXT
if [[ "${COMPANY_AGENT_ENABLE_CONFIGURED_KNOWLEDGE:-}" != "1" ]]; then
  unset COMPANY_AGENT_KNOWLEDGE_PATH
fi
export COMPANY_AGENT_PYTHON
export COMPANY_AGENT_PYTHONPATH="${ROOT}/src"
export COMPANY_AGENT_CONTRACTS_DIR="${ROOT}/contracts"
export COMPANY_AGENT_PRESET_ROOT="${presets_root}"
export COMPANY_AGENT_SKILL_ROOT="${skills_dst}"
export COMPANY_AGENT_DSH_ENTRY="${DSH_ENTRY}"
PORT="${COMPANY_AGENT_DSH_PORT:-3081}"
if [[ ! "${PORT}" =~ ^[0-9]+$ ]] || (( PORT < 1 || PORT > 65535 )); then
  echo "COMPANY_AGENT_DSH_PORT must be an integer from 1 to 65535" >&2
  exit 2
fi
export COMPANY_AGENT_DSH_PORT="${PORT}"
if [[ "${COMPANY_AGENT_MANAGED_ACCESS:-0}" == "1" ]]; then
  if [[ "${DEPLOYMENT_MODE}" != "development" ]]; then
    echo "managed local access is development-only; production requires explicit provider services" >&2
    exit 2
  fi
  export PYTHONPATH="${ROOT}/src"
  exec "${COMPANY_AGENT_PYTHON}" -P -m company_agent.access_runtime -- \
    "${NODE_BIN}" "${ROOT}/scripts/dsh-cli.mjs" --profile "${PROFILE}" --host 127.0.0.1 --port "${PORT}" --no-open
fi
exec "${NODE_BIN}" "${ROOT}/scripts/dsh-cli.mjs" --profile "${PROFILE}" --host 127.0.0.1 --port "${PORT}" --no-open
