#!/usr/bin/env bash
set -euo pipefail
umask 077
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DSH_HOME="${COMPANY_AGENT_DSH_HOME:-${XDG_CACHE_HOME:-${HOME}/.cache}/unitqc-company-agent/dsh-home}"
RUNTIME_SOURCE="${ROOT}/runtime"
RUNTIME="${COMPANY_AGENT_RUNTIME_DIR:-${XDG_CACHE_HOME:-${HOME}/.cache}/unitqc-company-agent/dsh-runtime}"
DSH_VERSION="0.1.5-rc.2"
NODE_PACKAGE_VERSION="22.22.0"
PNPM_VERSION="12.5.1"
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
mkdir -p "${DSH_HOME}" "${RUNTIME}"
chmod 700 "${DSH_HOME}" "${RUNTIME}"
rm -rf -- "${DSH_HOME}/profiles"
mkdir -p "${DSH_HOME}/profiles"
ln -s "${ROOT}/profiles/company-agent" "${DSH_HOME}/profiles/company-agent"
ln -s "${ROOT}/profiles/company-agent-minimal" "${DSH_HOME}/profiles/company-agent-minimal"
cp -f "${RUNTIME_SOURCE}/package.json" "${RUNTIME_SOURCE}/pnpm-lock.yaml" "${RUNTIME}/"
(
  cd "${RUNTIME}"
  corepack "pnpm@${PNPM_VERSION}" install --prod --ignore-scripts --frozen-lockfile --trust-lockfile
)
NODE_BIN="${RUNTIME}/node_modules/node/bin/node"
DSH_MANIFEST="${RUNTIME}/node_modules/@deepseek-ai/dsh/package.json"
if [[ ! -x "${NODE_BIN}" || ! -f "${DSH_MANIFEST}" ]]; then
  echo "pinned DSH runtime installation is incomplete" >&2
  exit 1
fi
if [[ "$("${NODE_BIN}" --version)" != "v${NODE_PACKAGE_VERSION}" ]]; then
  echo "installed Node version does not match ${NODE_PACKAGE_VERSION}" >&2
  exit 1
fi
DSH_INSTALLED_VERSION="$("${NODE_BIN}" -e 'console.log(JSON.parse(require("node:fs").readFileSync(process.argv[1], "utf8")).version)' "${DSH_MANIFEST}")"
if [[ "${DSH_INSTALLED_VERSION}" != "${DSH_VERSION}" ]]; then
  echo "installed DSH version does not match ${DSH_VERSION}" >&2
  exit 1
fi
for profile in company-agent company-agent-minimal; do
  profile_dir="${ROOT}/profiles/${profile}"
  (cd "${profile_dir}" && corepack "pnpm@${PNPM_VERSION}" install --prod --ignore-scripts --frozen-lockfile --trust-lockfile)
  if [[ "${profile}" == "company-agent-minimal" ]]; then
    rm -rf "${profile_dir}/node_modules/@unitqc/company-agent-device"
  fi
done
printf 'DSH_HOME=%s\n' "${DSH_HOME}"
