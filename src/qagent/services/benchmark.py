"""L1-04 algorithm acceptance gate. Field-name contract only. No science I/O."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from qagent.adapters.contracts import ROOT
from qagent.services.engines import list_engines

FIELD_VERSION = "version"
FIELD_CASES = "cases"
FIELD_PACK_ID = "pack_id"
FIELD_INVOKE_TOOL = "invoke_tool"
FIELD_REQUIRED_INPUT = "required_input_fields"
FIELD_REQUIRED_OUTPUT = "required_output_fields"
FIELD_FORBIDDEN_OUTPUT = "forbidden_output_fields"
FIELD_OUTPUT_CONST = "output_const"

_REQUIRED_CASE_FIELDS = (FIELD_PACK_ID, FIELD_INVOKE_TOOL, FIELD_REQUIRED_OUTPUT)
_DEFAULT_FIXTURE = ROOT / "tests" / "fixtures" / "benchmark_v1.json"


def load_fixture(path: Path | None = None) -> dict[str, Any]:
    """Parse the frozen benchmark fixture. Does not invoke packs or Twin."""
    target = Path(path) if path is not None else _DEFAULT_FIXTURE
    raw = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("benchmark fixture must be an object")
    cases = raw.get(FIELD_CASES)
    if not isinstance(cases, list):
        raise ValueError("benchmark fixture missing cases")
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("benchmark case must be an object")
        for key in _REQUIRED_CASE_FIELDS:
            if key not in case:
                raise ValueError(f"benchmark case missing {key}")
        outputs = case[FIELD_REQUIRED_OUTPUT]
        if not isinstance(outputs, list) or not all(isinstance(item, str) for item in outputs):
            raise ValueError("required_output_fields must be a list of names")
    return raw


def missing_pack_tests(
    test_root: Path,
    engine_ids: Sequence[str] | None = None,
) -> list[str]:
    """Wired pack ids with no fixture case or no test_*.py mention.

    「无单测 = fail」: a later wired engine without both a fixture case and a
    test file that mentions its id is listed here.
    """
    wired = _wired_ids(engine_ids)
    covered = _fixture_pack_ids(load_fixture())
    mentioned = _mentioned_in_tests(Path(test_root), wired)
    missing: list[str] = []
    seen: set[str] = set()
    for pack_id in wired:
        if pack_id in seen:
            continue
        seen.add(pack_id)
        if pack_id not in covered or pack_id not in mentioned:
            missing.append(pack_id)
    return missing


def _wired_ids(engine_ids: Sequence[str] | None) -> list[str]:
    if engine_ids is not None:
        return [str(item) for item in engine_ids]
    return [pack.id for pack in list_engines()]


def _fixture_pack_ids(raw: Mapping[str, Any]) -> set[str]:
    found: set[str] = set()
    for case in raw.get(FIELD_CASES) or []:
        if isinstance(case, Mapping) and case.get(FIELD_PACK_ID):
            found.add(str(case[FIELD_PACK_ID]))
    return found


def _mentioned_in_tests(test_root: Path, pack_ids: Iterable[str]) -> set[str]:
    wanted = [pack_id for pack_id in pack_ids if pack_id]
    if not wanted or not test_root.exists():
        return set()
    blobs: list[str] = []
    for path in sorted(test_root.rglob("test_*.py")):
        if path.is_file():
            blobs.append(path.read_text(encoding="utf-8"))
    text = "\n".join(blobs)
    return {pack_id for pack_id in wanted if pack_id in text}
