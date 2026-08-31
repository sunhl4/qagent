from qagent.services.eval_run import run_evals


def test_all_evals() -> None:
    results = {row.id: row for row in run_evals(*[f"E{i:02d}" for i in range(1, 22)])}
    assert len(results) == 21
    for eval_id, row in results.items():
        assert row.ok, f"{eval_id}: {row.detail}"
