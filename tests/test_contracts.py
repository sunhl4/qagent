from qagent.adapters.contracts import load_eval_cases, load_slots, load_tool_catalog
from qagent.models.gov import GOV_EVAL_IDS
from qagent.services.eval_run import DEFAULT_EVAL_IDS


def test_every_catalog_tool_has_schema_name() -> None:
    for spec in load_tool_catalog():
        assert spec.schema["name"] == spec.name
        assert spec.schema.get("parameters")
        assert spec.schema.get("output")


def test_eval_ids_are_e01_e18() -> None:
    ids = [c.id for c in load_eval_cases()]
    assert ids[:21] == [f"E{i:02d}" for i in range(1, 22)]
    assert "E22" in ids
    assert set(GOV_EVAL_IDS) <= set(ids)
    assert "E23" not in ids
    implemented = {c.id for c in load_eval_cases() if c.status == "implemented"}
    assert implemented == set(DEFAULT_EVAL_IDS)


def test_eval_slots_exist() -> None:
    slot_ids = {s.id for s in load_slots()}
    for case in load_eval_cases():
        assert case.slot in slot_ids, case.id


def test_tool_slots_exist() -> None:
    slot_ids = {s.id for s in load_slots()}
    for spec in load_tool_catalog():
        assert spec.slot in slot_ids, spec.name


def test_compile_estimate_forbids_signoff_ok() -> None:
    spec = next(s for s in load_tool_catalog() if s.name == "ionstack_compile_estimate")
    assert "ok" in spec.schema["forbidden_output_keys"]


def test_get_job_forbids_bitstrings() -> None:
    spec = next(s for s in load_tool_catalog() if s.name == "qdata_get_job")
    assert "bitstrings" in spec.schema["forbidden_output_keys"]
