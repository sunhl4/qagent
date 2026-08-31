#!/usr/bin/env bash
set -euo pipefail

QAGENT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DSH_HOME="${QAGENT_ROOT}/.dsh-home"
RUNTIME="${QAGENT_ROOT}/.dsh-runtime"
PROFILE_SRC="${QAGENT_ROOT}/profiles/qagent"
DSH_VER="0.1.0-rc.8"
DSH_BIN="${RUNTIME}/node_modules/.bin/dsh"

mkdir -p "${DSH_HOME}/profiles" "${RUNTIME}"
ln -sfn "${PROFILE_SRC}" "${DSH_HOME}/profiles/qagent"

cd "${RUNTIME}"
if [[ ! -f package.json ]]; then
  cat > package.json <<EOF
{
  "name": "qagent-dsh-runtime",
  "private": true,
  "dependencies": {
    "@deepseek-ai/dsh": "${DSH_VER}"
  }
}
EOF
fi
if [[ ! -x "${DSH_BIN}" ]]; then
  if command -v pnpm >/dev/null 2>&1; then
    pnpm add --prod --ignore-scripts "@deepseek-ai/dsh@${DSH_VER}"
  else
    npm install --omit=dev --no-fund --no-audit --prefer-offline --fetch-retries=5 "@deepseek-ai/dsh@${DSH_VER}"
  fi
fi

cd "${PROFILE_SRC}"
mkdir -p node_modules/@qccd
for pkg in brand cards docs eln engines policy qchem qdata qiskit route twin; do
  ln -sfn "../../../../packages/qagent-${pkg}" "node_modules/@qccd/qagent-${pkg}"
done
if [[ ! -d node_modules/@deepseek-ai/dsh-subagent-codex || ! -d node_modules/@openai/codex ]]; then
  if command -v pnpm >/dev/null 2>&1; then
    pnpm install --prod --ignore-scripts
  else
    npm install --omit=dev --no-fund --no-audit --prefer-offline --fetch-retries=5
  fi
fi

if [[ ! -x "${DSH_BIN}" ]]; then
  echo "dsh binary missing after npm install" >&2
  exit 1
fi

# H-01g: profile dsh-tools 必须和宿主 agent-loop 是同一份模块。
# 两份拷贝 = TOOL_RUNTIME_SCHEDULER 对不上，点工具时 prepare 是 undefined。
_host_tools=""
if [[ -d "${RUNTIME}/node_modules/.pnpm" ]]; then
  _host_tools="$(find "${RUNTIME}/node_modules/.pnpm" \
    -path '*@deepseek-ai+dsh-tools@*/node_modules/@deepseek-ai/dsh-tools' \
    -type d | head -n 1)"
fi
_profile_tools="${PROFILE_SRC}/node_modules/@deepseek-ai/dsh-tools"
if [[ -n "${_host_tools}" && -d "${_host_tools}" ]]; then
  mkdir -p "$(dirname "${_profile_tools}")"
  if [[ "$(realpath "${_profile_tools}" 2>/dev/null || true)" != "$(realpath "${_host_tools}")" ]]; then
    rm -rf "${_profile_tools}"
    ln -sfn "${_host_tools}" "${_profile_tools}"
  fi
fi
unset _host_tools _profile_tools

export DSH_HOME
echo "DSH_HOME=${DSH_HOME}"
echo "boot: DSH_HOME=${DSH_HOME} ${DSH_BIN} --profile qagent"
"${DSH_BIN}" --profile qagent --dump-config >"${RUNTIME}/qagent-dsh-dump.yml"
echo "dump-config wrote ${RUNTIME}/qagent-dsh-dump.yml"
