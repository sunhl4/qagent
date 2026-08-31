import json
from pathlib import Path

from qagent.adapters.contracts import ROOT


def test_runtime_pins() -> None:
    pins = json.loads((ROOT / "pins.json").read_text(encoding="utf-8"))
    assert pins["deepseek_harness"]["version"] == "0.1.0-rc.8"
    assert pins["openai_codex"]["version"] == "0.147.0"
    assert pins["dsh_subagent_codex"]["version"] == "0.1.0-rc.8"
