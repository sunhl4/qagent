#!/usr/bin/env bash
# Optional dsh runtime for Cursor / Code Mode. Not the human product face.
set -euo pipefail
QAGENT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export DSH_HOME="${QAGENT_ROOT}/.dsh-home"
if [[ -f "${QAGENT_ROOT}/.qagent/dsh.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${QAGENT_ROOT}/.qagent/dsh.env"
  set +a
fi
# H-01h: 产品 3081 默认 lab。algo 仍可显式 export / 写进 dsh.env。
# 文件赢过环境；测留下的 sign/algo 不能挡 3080「扫氢分子」。
export QAGENT_PRESET="${QAGENT_PRESET:-lab}"
_preset_file="${QAGENT_PRESET_FILE:-${QAGENT_ROOT}/.qagent/active_preset}"
mkdir -p "$(dirname "${_preset_file}")"
if [[ "$(tr -d '[:space:]' < "${_preset_file}" 2>/dev/null || true)" != "${QAGENT_PRESET}" ]]; then
  printf '%s\n' "${QAGENT_PRESET}" > "${_preset_file}"
fi
unset _preset_file
# H-01h 单测：只跑到写 preset 就退出，不 exec dsh。
if [[ "${QAGENT_H01H_HEAL_ONLY:-}" == "1" ]]; then
  exit 0
fi
# H-03g: 空 HOME 从 workplace.json 补 export。环境里已有非空值不覆盖。
# 只认四个字段。永不读 secrets.json。永不 export QAGENT_CLOUD_URL / 密钥。
_workplace_file="${QAGENT_WORKPLACE_FILE:-${QAGENT_ROOT}/.qagent/workplace.json}"
while IFS= read -r _home_line || [[ -n "${_home_line}" ]]; do
  case "${_home_line}" in
    QAGENT_QDATA_HOME=*|QAGENT_QCHEM_HOME=*|QAGENT_IONSTACK_HOME=*|QAGENT_KNOWLEDGE_PATH=*)
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
DSH_BIN="${QAGENT_ROOT}/.dsh-runtime/node_modules/.bin/dsh"
if [[ ! -x "${DSH_BIN}" ]]; then
  echo "dsh missing; run scripts/bootstrap_wp0.sh first" >&2
  exit 1
fi
PRESET_SRC="${QAGENT_ROOT}/profiles/qagent/agent-presets/qagent"
PRESET_DST="${DSH_HOME}/.agent-presets/qagent"
if [[ -f "${PRESET_SRC}/agent.cordis.yml" ]]; then
  mkdir -p "${PRESET_DST}"
  cp -f "${PRESET_SRC}/agent.cordis.yml" "${PRESET_SRC}/preset.yml" "${PRESET_DST}/"
fi
# skills sync — copy profile-visible skills into $DSH_HOME/skills.
# Do not touch DSH_HOME credentials (.credentials.yaml).
SKILLS_SRC="${QAGENT_ROOT}/skills"
SKILLS_DST="${DSH_HOME}/skills"
VISIBILITY="${QAGENT_ROOT}/profiles/qagent/skill-visibility.json"
mkdir -p "${SKILLS_DST}"
python3 - "${VISIBILITY}" "${SKILLS_SRC}" "${SKILLS_DST}" "${QAGENT_PRESET}" <<'PY'
import json
import shutil
import sys
from pathlib import Path

vis, src, dst, preset = sys.argv[1:5]
data = json.loads(Path(vis).read_text(encoding="utf-8"))
src_p, dst_p = Path(src), Path(dst)
rows = data["skills"]
managed = {row["id"] for row in rows}
wanted = {row["id"] for row in rows if preset in row["visible"]}
if dst_p.is_dir():
    for child in dst_p.iterdir():
        if child.name in managed and child.name not in wanted:
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
for name in sorted(wanted):
    skill_src = src_p / name / "SKILL.md"
    if not skill_src.is_file():
        raise SystemExit(f"missing skill {name}")
    skill_dst = dst_p / name
    skill_dst.mkdir(parents=True, exist_ok=True)
    shutil.copy2(skill_src, skill_dst / "SKILL.md")
PY
export QAGENT_DSH_AGENT_PRESET="${QAGENT_DSH_AGENT_PRESET:-qagent}"
# H-01g: profile dsh-tools 必须和宿主 agent-loop 是同一份模块。
# 两份拷贝 = TOOL_RUNTIME_SCHEDULER 对不上，点工具时 prepare 是 undefined。
_host_tools=""
if [[ -d "${QAGENT_ROOT}/.dsh-runtime/node_modules/.pnpm" ]]; then
  _host_tools="$(find "${QAGENT_ROOT}/.dsh-runtime/node_modules/.pnpm" \
    -path '*@deepseek-ai+dsh-tools@*/node_modules/@deepseek-ai/dsh-tools' \
    -type d | head -n 1)"
fi
_profile_tools="${QAGENT_ROOT}/profiles/qagent/node_modules/@deepseek-ai/dsh-tools"
if [[ -n "${_host_tools}" && -d "${_host_tools}" ]]; then
  mkdir -p "$(dirname "${_profile_tools}")"
  if [[ "$(realpath "${_profile_tools}" 2>/dev/null || true)" != "$(realpath "${_host_tools}")" ]]; then
    rm -rf "${_profile_tools}"
    ln -sfn "${_host_tools}" "${_profile_tools}"
  fi
fi
unset _host_tools _profile_tools
exec "${DSH_BIN}" --profile qagent --host 127.0.0.1 --port "${QAGENT_DSH_PORT:-3081}" --no-open
