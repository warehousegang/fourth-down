"""Independent RC1 synthetic lifecycle oracles and production-isolation checks."""
import json
import math
from pathlib import Path

import pytest

from ml.current_source import sha
from ml.data import ROOT
from ml.lifecycle_simulation import CASES, allowed_output, run_scenarios


@pytest.fixture(scope="module")
def simulation(tmp_path_factory):
    output = tmp_path_factory.mktemp("synthetic-lifecycle-report")
    receipt = run_scenarios(output)
    body = Path(receipt["artifact"]).read_bytes()
    assert sha(body) == receipt["sha256"]
    return receipt, json.loads(body)


@pytest.mark.parametrize("case_id", [case[0] for case in CASES])
def test_required_scenarios_pass_with_explicit_synthetic_provenance(simulation, case_id):
    receipt, data = simulation
    scenario = next(row for row in data["scenarios"] if row["id"] == case_id)
    assert scenario["synthetic"] and all(scenario["checks"].values())
    assert scenario["checks"]["original_forecast_bytes_and_pointer_immutable"]
    assert scenario["checks"]["pregame_operations_bytes_immutable"]
    for source in scenario["input_snapshots"]:
        assert source["synthetic"] and "SYNTHETIC" in source["source_name"]
        assert source["source_url"].startswith("https://example.invalid/")
        assert all("synthetic-" in g["id"] and g["season"] == 2026 for g in source["games"])
    for record in scenario["artifacts"]:
        from ml.current_source import canonical
        assert record["sha256"] == sha(canonical(record["payload"]))
        if record["kind"] == "synthetic-forecast":
            assert "SYNTHETIC" in record["payload"]["source"]["source_name"]
    assert receipt["scenario_count"] == data["scenario_count"] == 14
    assert data["real_nfl_outcomes_consumed"] == data["model_fits"] == data["network_calls"] == data["production_writes"] == 0


def test_independent_raw_feature_and_probability_derivation(simulation):
    _, data = simulation
    home_favorite = next(s for s in data["scenarios"] if s["id"] == "strong_favorite_loses")
    underdog = next(s for s in data["scenarios"] if s["id"] == "underdog_wins")
    frozen = json.loads((ROOT/"docs/FROZEN_MODEL.json").read_bytes())["model"]
    # Four controlled wins/losses, ±20 points. Both teams last played seven days ago.
    expected = {"smooth_win_diff": .75-.25, "margin_diff": 80/8-(-80/8),
                "recent_margin_diff": 80/6-(-80/6), "rest_diff": 0}
    assert home_favorite["features"] == expected
    assert underdog["features"] == {k:-v for k,v in expected.items()}
    for scenario in (home_favorite, underdog):
        z = frozen["intercept"] + sum(scenario["features"][f]*c for f,c in zip(frozen["features"],frozen["coefficients"]))
        assert scenario["home_probability"] == pytest.approx(1/(1+math.exp(-z)),abs=1e-14)
    assert home_favorite["home_probability"] > .8 and underdog["home_probability"] < .2
    assert home_favorite["home_probability"] != .8  # No requested probability forced into the model.


def test_independent_arithmetic_for_every_synthetic_scored_snapshot(simulation):
    _, data = simulation
    count = 0
    for scenario in data["scenarios"]:
        for record in scenario["artifacts"]:
            if record["kind"] != "synthetic-operations":
                continue
            for game in record["payload"]["games"]:
                for score in game["evaluations"]:
                    count += 1
                    p,y = score["home_probability"],score["outcome_home"]
                    assert score["correct"] == ((p>=.5)==bool(y))
                    assert score["brier"] == pytest.approx((p-y)**2,abs=1e-14)
                    expected = -(y*math.log(p)+(1-y)*math.log(1-p))
                    assert score["log_loss"] == score["surprise"] == pytest.approx(expected,abs=1e-14)
    assert count == 7  # Six evaluated scenarios; corrected-final retains two evaluations.


def test_uncertainty_is_not_a_causal_or_model_accuracy_claim(simulation):
    _, data = simulation
    assert any("not NFL predictive accuracy" in limitation for limitation in data["limitations"])
    for scenario in data["scenarios"]:
        for record in scenario["artifacts"]:
            if record["kind"] == "synthetic-operations":
                for game in record["payload"]["games"]:
                    analysis = game["analysis"]
                    if analysis:
                        assert analysis["deficiencies"] == []
                        assert all(h["evidence_needed"] for h in analysis["hypotheses"])
                        assert analysis["agent_boundary"]["paid_calls"] == 0
                        assert all(not any(term in f["text"].lower() for term in ("caused", "injury", "weather", "quarterback")) for f in analysis["facts"])


def test_expected_statuses_and_zero_score_cases(simulation):
    _, data = simulation
    cases = {s["id"]:s for s in data["scenarios"]}
    assert cases["missing_final"]["status_transitions"] == ["scheduled","unknown"]
    assert cases["postponed"]["status_transitions"] == ["scheduled","postponed"]
    assert cases["in_progress"]["status_transitions"] == ["scheduled","in_progress"]
    for name in ("missing_final","postponed","in_progress","missing_source","failed_generation","stale_source","missing_feature_input","tied_final"):
        assert cases[name]["scored_games"] == 0 and cases[name]["final_metrics"]["primary"]["brier"] is None
    assert cases["tied_final"]["final_metrics"]["primary"]["ties_excluded"] == 1


def test_corrected_score_preserves_both_versions_and_original_probability(simulation):
    _,data = simulation
    case = next(s for s in data["scenarios"] if s["id"] == "corrected_final")
    completed = [a for a in case["artifacts"] if a["kind"]=="synthetic-operations" and a["payload"]["games"][0]["result"]]
    first,second = [a["payload"]["games"][0] for a in completed]
    assert completed[0]["sha256"] != completed[1]["sha256"]
    assert first["result"]["version"] != second["result"]["version"]
    assert first["evaluations"][0]["home_probability"] == second["evaluations"][0]["home_probability"] == case["home_probability"]
    assert first["evaluations"][0]["correct"] and not second["evaluations"][0]["correct"]


def test_late_injury_and_duplicate_event_invariants(simulation):
    _,data = simulation
    cases = {s["id"]:s for s in data["scenarios"]}
    annotation = cases["late_injury_context"]["annotation"]
    assert annotation["status"]=="unavailable" and annotation["probability_adjustment"] is None
    assert "Future" in annotation["rejected"][0]["reason"]
    assert cases["duplicate_events"]["final_metrics"]["primary"]["count"]==1
    assert cases["duplicate_events"]["checks"]["duplicate_event_and_run_are_idempotent"]
    assert "Duplicate forecast artifact" in cases["duplicate_events"]["failures"][0]["message"]


def test_repeated_runs_are_byte_identical(simulation, tmp_path):
    receipt,_ = simulation
    repeated = run_scenarios(tmp_path)
    assert repeated["sha256"] == receipt["sha256"]
    assert Path(repeated["artifact"]).read_bytes() == Path(receipt["artifact"]).read_bytes()


def test_network_fit_and_production_publication_are_forbidden(tmp_path, monkeypatch):
    from ml import current_source, lifecycle_simulation as module
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline
    def forbidden(*args, **kwargs):
        pytest.fail("Synthetic scenario harness attempted network or fitting")
    monkeypatch.setattr(current_source,"download",forbidden)
    for cls in (LogisticRegression,StandardScaler,Pipeline):monkeypatch.setattr(cls,"fit",forbidden)
    monkeypatch.setattr(StandardScaler,"partial_fit",forbidden)
    frozen_before = (ROOT/"docs/FROZEN_MODEL.json").read_bytes()
    public_before = {str(p.relative_to(ROOT)):sha(p.read_bytes()) for p in (ROOT/"web/public/data").rglob("*.json")}
    original_forecast,original_operations = module.publish_local,module.publish_operations
    calls=[]
    def local_only(function):
        def publish(artifact, directory=None):
            assert directory is not None and "fourth-down-rc1-synthetic-" in str(directory)
            assert not Path(directory).resolve().is_relative_to(ROOT.resolve())
            calls.append(str(directory))
            return function(artifact,directory)
        return publish
    monkeypatch.setattr(module,"publish_local",local_only(original_forecast))
    monkeypatch.setattr(module,"publish_operations",local_only(original_operations))
    run_scenarios(tmp_path)
    assert calls and len([p for p in calls if p.endswith("/current")])==14
    assert (ROOT/"docs/FROZEN_MODEL.json").read_bytes() == frozen_before
    assert public_before == {str(p.relative_to(ROOT)):sha(p.read_bytes()) for p in (ROOT/"web/public/data").rglob("*.json")}


@pytest.mark.parametrize("relative", ["web/public/data/current","web/public/data/operations","data/current/2026","artifacts/model.json","docs"])
def test_output_rejects_production_or_unapproved_paths(relative):
    with pytest.raises(ValueError,match="Synthetic output"):
        allowed_output(ROOT/relative)


def test_temporary_symlink_cannot_redirect_into_production(tmp_path):
    destination = tmp_path/"escape"
    destination.symlink_to(ROOT/"web/public/data",target_is_directory=True)
    with pytest.raises(ValueError,match="Synthetic output"):
        allowed_output(destination)


def test_unexpected_generation_failure_does_not_publish_a_pass_report(tmp_path,monkeypatch):
    from ml import lifecycle_simulation as module
    def failed(*args,**kwargs):raise RuntimeError("injected generation failure")
    monkeypatch.setattr(module,"generate",failed)
    output=tmp_path/"never-published"
    with pytest.raises(RuntimeError,match="injected generation"):
        run_scenarios(output)
    assert not output.exists()
