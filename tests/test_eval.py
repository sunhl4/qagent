from qagent.models.gov import HUB_EVAL_IDS
from qagent.services.eval_run import run_evals


def test_all_evals() -> None:
    results = {row.id: row for row in run_evals(*[f"E{i:02d}" for i in range(1, 22)])}
    assert len(results) == 21
    for eval_id, row in results.items():
        assert row.ok, f"{eval_id}: {row.detail}"


def test_hub_evals() -> None:
    results = {row.id: row for row in run_evals(*HUB_EVAL_IDS)}
    assert set(results) == set(HUB_EVAL_IDS)
    for eval_id, row in results.items():
        assert row.ok, f"{eval_id}: {row.detail}"
