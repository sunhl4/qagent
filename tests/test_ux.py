"""G-02: error catalog, lamps, preset read face. Slot id is not a reason."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT
SHELL = ROOT / "apps" / "customer-shell"
sys.path.insert(0, str(ROOT / "src"))

from qagent.adapters.docs import WiredDocs
from qagent.adapters.pin import NativePin
from qagent.adapters.preset import active_preset, set_active_preset
from qagent.entrypoints.shell_http import dispatch
from qagent.models.errors import CODE_ESTIMATE_MISSING, KIND_MISSING, classify_kind, code_for
from qagent.models.life import life_labels
from qagent.services.errors import lookup_error
from qagent.services.invoke import invoke

_ENV_KEYS = (
    "QAGENT_PRESET_FILE",
    "QAGENT_PRESET",
    "QAGENT_ASSIGNMENTS_FILE",
    "QAGENT_ELN_FILE",
    "QAGENT_ASKS_FILE",
    "QAGENT_USAGE_FILE",
    "QAGENT_SHELL_TOKEN",
)
_NOTE = REPO / "docs" / "execution" / "G-02_ux.md"


@contextmanager
def isolated() -> Iterator[Path]:
    previous = {key: os.environ.get(key) for key in _ENV_KEYS}
    tmp = tempfile.TemporaryDirectory()
    try:
        folder = Path(tmp.name)
        os.environ["QAGENT_PRESET_FILE"] = str(folder / "active_preset")
        os.environ.pop("QAGENT_PRESET", None)
        os.environ["QAGENT_ASSIGNMENTS_FILE"] = str(folder / "assignments.jsonl")
        os.environ["QAGENT_ELN_FILE"] = str(folder / "eln.jsonl")
        os.environ["QAGENT_ASKS_FILE"] = str(folder / "asks.jsonl")
        os.environ["QAGENT_USAGE_FILE"] = str(folder / "usage.jsonl")
        os.environ.pop("QAGENT_SHELL_TOKEN", None)
        yield folder
    finally:
        tmp.cleanup()
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_catalog_explains_estimate_slot() -> None:
    kind = classify_kind("ionstack_compile_estimate", "circuit.body or circuit_id is required")
    assert kind == KIND_MISSING
    assert code_for("ionstack_compile_estimate", kind) == CODE_ESTIMATE_MISSING
    row = lookup_error(slot="S-TWIN-03")
    codes = {item.get("code") for item in row["entries"]}
    assert "ESTIMATE_MISSING" in codes
    assert "ESTIMATE_UNREADY" in codes
    assert "ESTIMATE_REFUSED" in codes
    code, payload = dispatch("GET", "/api/errors?slot=S-TWIN-03")
    assert code == 200
    assert payload["note"]
    assert payload["entries"]


def test_list_engines_announces_switch() -> None:
    with isolated():
        set_active_preset("lab")
        listed = invoke("qagent_list_engines", "lab", {})
        assert listed.status == "ok"
        assert "switched" not in (listed.payload or {})
        assert active_preset() == "lab"
        switched = invoke("qagent_list_engines", "lab", {"preset": "sign"})
        assert switched.status == "ok"
        face = switched.payload or {}
        assert face["active_preset"] == "sign"
        assert face["switched"] is True
        assert face["previous_preset"] == "lab"
        assert "切会话" in str(face.get("hint") or "")


def test_preset_http_read_vs_write() -> None:
    with isolated():
        set_active_preset("lab")
        code, face = dispatch("GET", "/api/preset")
        assert code == 200
        assert face["active_preset"] == "lab"
        assert active_preset() == "lab"
        denied = dispatch("POST", "/api/preset", {"preset": "sign"}, {})
        assert denied[0] == 403
        assert active_preset() == "lab"
        os.environ["QAGENT_SHELL_TOKEN"] = "ux-token"
        ok = dispatch(
            "POST",
            "/api/preset",
            {"preset": "sign"},
            {"X-QAGENT-DEBUG-TOKEN": "ux-token"},
        )
        assert ok[0] == 200
        assert ok[1]["active_preset"] == "sign"
        assert ok[1]["previous_preset"] == "lab"
        assert ok[1]["switched"] is True


def test_gov_face_has_lamps() -> None:
    with isolated():
        code, payload = dispatch("GET", "/api/gov/face")
        assert code == 200
        lamps = payload["lamps"]
        for key in ("twin", "estimate", "qdata", "asks"):
            assert key in lamps
        assert "twin_id" not in json.dumps(payload)
        assert isinstance(payload["life"], list)
        for label in payload["life"]:
            assert "ionstack_" not in str(label)


def test_pin_qiskit_needs_body() -> None:
    try:
        NativePin().pin_circuit({"source": "qiskit", "asset_id": "asset_only"})
    except ValueError as exc:
        text = str(exc)
        assert "source=qiskit" in text
        assert "qasm3 or logical" in text
    else:
        raise AssertionError("qiskit pin with only asset_id must fail")


def test_export_needs_context() -> None:
    missed = invoke("qiskit_export_circuit", "lab", {})
    assert missed.status == "error"
    assert "circuit_id" in (missed.error or "")
    assert missed.explain
    assert missed.explain.get("kind") == KIND_MISSING
    assert missed.explain.get("code") == "PIN_MISSING"


def test_docs_hit_error_codes() -> None:
    hits = WiredDocs().search({"query": "S-TWIN-03"})
    assert hits.get("empty") is False
    blob = " ".join(item.get("text") or "" for item in hits.get("hits") or [])
    assert "S-TWIN-03" in blob
    assert "填充" in blob or "fill" in blob.lower() or "不是原因" in blob or "不是错误原因" in blob


def test_life_hides_tool_names() -> None:
    labels = life_labels(
        ["qagent_pin_circuit", "ionstack_compile_estimate", "ionstack_twin_run"]
    )
    assert labels == ["线路", "预估", "签收"]


def test_shell_keeps_rails() -> None:
    js = (SHELL / "app.js").read_text(encoding="utf-8")
    html = (SHELL / "index.html").read_text(encoding="utf-8")
    assert "ionstack_twin_run" not in js
    assert "twin_id=" not in js
    assert 'id="gov-lamps"' in html
    assert "孪生" in js
    assert "预估" in js
    http = (ROOT / "src" / "qagent" / "entrypoints" / "shell_http.py").read_text(encoding="utf-8")
    assert "twin_id" not in http


def test_note_exists() -> None:
    assert _NOTE.is_file()
    text = _NOTE.read_text(encoding="utf-8")
    assert "S-TWIN-03" in text
    assert "不改工具名" in text


def main() -> int:
    failed = 0
    for name, fn in (
        ("catalog_explains_estimate_slot", test_catalog_explains_estimate_slot),
        ("list_engines_announces_switch", test_list_engines_announces_switch),
        ("preset_http_read_vs_write", test_preset_http_read_vs_write),
        ("gov_face_has_lamps", test_gov_face_has_lamps),
        ("pin_qiskit_needs_body", test_pin_qiskit_needs_body),
        ("export_needs_context", test_export_needs_context),
        ("docs_hit_error_codes", test_docs_hit_error_codes),
        ("life_hides_tool_names", test_life_hides_tool_names),
        ("shell_keeps_rails", test_shell_keeps_rails),
        ("note_exists", test_note_exists),
    ):
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
