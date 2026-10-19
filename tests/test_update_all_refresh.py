from pipelines.importers import update_all


def test_refresh_runs_all_analytics_stages_in_order(monkeypatch):
    calls = []
    monkeypatch.setattr(
        update_all.subprocess, "run",
        lambda command, cwd, check: calls.append((command, cwd, check)),
    )
    update_all.refresh_analytics()
    assert [call[0][1] for call in calls] == [
        "materialize_stage1.py", "seed_stage2_cogs.py", "materialize_stage3.py",
    ]
    assert all(call[2] for call in calls)
