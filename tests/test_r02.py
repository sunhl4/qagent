"""R-02: flex tools + fail-closed. No third loop. No minted twin_id."""

from __future__ import annotations

import inspect
import os
import tempfile
import traceback
from pathlib import Path

from qagent.adapters.contracts import load_policy
from qagent.models.handles import HANDLE_TWIN
from qagent.services.eval_run import DEFAULT_CIRCUIT
from qagent.services.invoke import invoke
from qagent.services.policy import decide

QROOT = Path(__file__).resolve().parents[1]
REPO = QROOT
RAILS = QROOT / "profiles" / "qagent" / "rails.md"
NOTE = REPO / "docs" / "execution" / "R-02_flex_tools.md"
POLICY_PY = QROOT / "src" / "qagent" / "services" / "policy.py"
CORDIS = QROOT / "profiles" / "qagent" / "agent-presets" / "qagent" / "agent.cordis.yml"
_SIGNED_LOOKING = frozenset({"ok", HANDLE_TWIN, "signoff", "signed", "signature"})
_KEEP_FORBIDDEN = (
    "cal_edit",
    "qiskit_ibm_run",
)


def _strip_yaml_comments(text: str) -> str:
    lines = []
    for line in text.splitlines():
        stripped = line.split("#", 1)[0].rstrip()
        if stripped:
            lines.append(stripped)
    return "\n".join(lines).strip()


def test_unknown_tool_and_no_rule_deny() -> None:
    assert decide("not_a_real_tool", "lab", {}) == "deny"
    assert decide("cal_edit", "lab", {}) == "deny"
    source = inspect.getsource(decide)
    assert "fail closed" in source.lower()
    assert source.rstrip().endswith('return "deny"')
    assert POLICY_PY.read_text(encoding="utf-8").rstrip().endswith('return "deny"')
    policy = load_policy()
    assert policy["fail_closed"] is True
    forbidden = set(policy["forbidden_tool_names"])
    assert set(_KEEP_FORBIDDEN) <= forbidden


def test_estimate_ok_no_signoff_no_twin() -> None:
    handle, name = tempfile.mkstemp(prefix="r02-eln-", suffix=".jsonl")
    os.close(handle)
    path = Path(name)
    previous = os.environ.get("QAGENT_ELN_FILE")
    os.environ["QAGENT_ELN_FILE"] = str(path)
    try:
        result = invoke(
            "ionstack_compile_estimate",
            "lab",
            {"circuit": DEFAULT_CIRCUIT},
        )
    finally:
        if previous is None:
            os.environ.pop("QAGENT_ELN_FILE", None)
        else:
            os.environ["QAGENT_ELN_FILE"] = previous
        path.unlink(missing_ok=True)
    assert result.decision == "allow"
    assert result.status == "ok"
    payload = dict(result.payload or {})
    assert "makespan_ns" in payload
    assert isinstance(payload["makespan_ns"], (int, float))
    leaked = _SIGNED_LOOKING & set(payload)
    assert not leaked, leaked
    assert HANDLE_TWIN not in payload
    assert "ok" not in payload


def test_twin_run_unapproved_needs_ask() -> None:
    result = invoke("ionstack_twin_run", "lab", {})
    assert result.decision == "ask"
    assert result.status == "needs_ask"
    assert result.payload is None
    assert HANDLE_TWIN not in dict(result.payload or {})


def test_rails_assets_first_no_invented_twin() -> None:
    assert RAILS.is_file()
    text = RAILS.read_text(encoding="utf-8")
    assert "资产优先" in text
    assert "禁止编造 twin_id" in text
    assert "twin_id" in text
    body = _strip_yaml_comments(CORDIS.read_text(encoding="utf-8"))
    assert body == "[]"


def test_note_exists() -> None:
    assert NOTE.is_file()
    text = NOTE.read_text(encoding="utf-8")
    assert "R-02" in text
    assert "rails.md" in text


def main() -> int:
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok  {name}")
            except Exception:
                failed += 1
                print(f"FAIL {name}")
                traceback.print_exc()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
