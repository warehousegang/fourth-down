"""Synthetic prospective lifecycle adversarial tests; no holdout data, network or fitting."""
import copy
import json
import math
from pathlib import Path

import pytest

from ml.current import generate, publish_local
from ml.current_source import canonical, sha, timestamp
from ml.lifecycle import (HOME_RATE, binary_score, build_operations, export_operations,
                          metric_set, publish_operations, status)

CAPTURES = []


@pytest.fixture(autouse=True)
def clear_captures():
    CAPTURES.clear()


BEFORE = "2026-09-12T13:00:00+00:00"
AFTER = "2026-09-14T03:00:00+00:00"


def scheduled(identifier="1", home="DET", away="GB"):
    return {"id": f"ngs-2026-{identifier}", "source_game_id": identifier, "season": 2026, "week": 1,
            "home": home, "away": away, "day": "2026-09-13", "kickoff": "2026-09-13T17:00:00+00:00",
            "home_score": None, "away_score": None, "phase": "", "validated": False, "stadium": "Synthetic test stadium"}


def snapshot(games=None, observed="2026-09-12T12:00:00+00:00"):
    return {"schema_version": 1, "season": 2026, "retrieved_at": observed, "source_updated_at": observed,
            "source_url": "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/nfl_ngs_schedules/ngs_schedule_2026.csv",
            "raw_sha256": "a"*64, "asset_id": 1, "source_name": "Synthetic test", "license_url": "https://example.test/license",
            "games": [scheduled()] if games is None else games}


def bundle(artifact):
    digest = sha(canonical(artifact))
    return {"file": f"forecast-{artifact['season']}-{digest}.json", "sha256": digest, "artifact": artifact}


def forecast(source=None, decision=BEFORE):
    source = source or snapshot()
    CAPTURES.append(copy.deepcopy(source))
    return generate(source, [], decision, decision)


def finals(source=None, home_score=20, away_score=10, observed="2026-09-13T23:00:00+00:00"):
    source = copy.deepcopy(source or snapshot())
    source["retrieved_at"] = source["source_updated_at"] = observed
    for game in source["games"]:
        game.update(phase="FINAL", validated=True, home_score=home_score, away_score=away_score)
    return source


def operation(artifacts=None, sources=None, generated=AFTER):
    inputs = [bundle(f) for f in (artifacts or [forecast()])]
    all_sources = {sha(canonical(s)): s for s in [*CAPTURES, *(sources or [finals()])]}
    return build_operations(inputs, list(all_sources.values()), generated)


def test_empty_prospective_sample_is_not_historical_performance():
    result = operation(sources=[snapshot()], generated=BEFORE)
    assert len(result["catalog"]) == len(result["games"]) == 1
    assert result["catalog"][0]["eligible"]
    assert result["games"][0]["final_forecast_id"] is None
    assert result["metrics"]["primary"]["count"] == 0
    assert result["metrics"]["primary"]["brier"] is None
    assert result["metrics"]["primary"]["calibration"][0]["mean_probability"] is None
    assert result["games"][0]["analysis"] is None


def test_verified_final_scores_preserved_probability_and_fixed_baselines():
    f = forecast()
    p = f["games"][0]["home_probability"]
    result = operation([f])
    row = result["games"][0]
    score = row["evaluations"][0]
    assert score["primary"] and row["final_forecast_id"] == score["forecast_id"]
    assert score["brier"] == pytest.approx((1-p)**2)
    assert score["log_loss"] == score["surprise"] == pytest.approx(-math.log(p))
    assert score["baseline"]["coin_flip"]["brier"] == .25
    assert score["baseline"]["home_rate"]["probability"] == HOME_RATE
    assert result["metrics"]["primary"]["count"] == 1
    assert sum(c["count"] for c in result["metrics"]["primary"]["calibration"]) == 1
    assert row["analysis"]["facts"] and not row["analysis"]["deficiencies"]
    assert row["analysis"]["agent_boundary"]["paid_calls"] == 0


def test_original_latest_final_and_every_snapshot_are_scored():
    first = forecast()
    second = forecast(decision="2026-09-12T14:00:00+00:00")
    result = operation([second, first])
    row = result["games"][0]
    assert row["original_forecast_id"] != row["latest_forecast_id"]
    assert row["final_forecast_id"] == row["latest_forecast_id"]
    assert len(row["evaluations"]) == 2
    assert result["metrics"]["primary"]["count"] == 1
    assert result["metrics"]["all_snapshots"]["count"] == 2
    assert result["metrics"]["all_snapshots"]["game_count"] == 1
    assert canonical(result) == canonical(operation([first, second]))


def test_display_ttl_expiry_does_not_erase_legitimate_pregame_forecast():
    f = forecast()
    assert timestamp(f["valid_until"]) < timestamp(f["games"][0]["kickoff"])
    result = operation([f])
    assert result["catalog"][0]["eligible"]
    assert result["metrics"]["primary"]["count"] == 1


@pytest.mark.parametrize("when", ["2026-09-13T17:00:00+00:00", "2026-09-13T18:00:00+00:00"])
def test_generated_at_or_after_kickoff_never_scored(when):
    f = forecast()
    f["generated_at"] = f["games"][0]["generated_at"] = when
    result = operation([f])
    assert not result["catalog"][0]["eligible"]
    assert result["metrics"]["primary"]["count"] == 0
    assert "before kickoff" in " ".join(result["catalog"][0]["exclusions"])


@pytest.mark.parametrize("changed", [{"home": "KC"}, {"away": "BUF"}, {"week": 2}, {"day": "2026-09-14", "kickoff": "2026-09-14T17:00:00+00:00"}])
def test_schedule_identity_correction_excludes_old_forecast(changed):
    source = finals(observed="2026-09-15T12:00:00+00:00")
    source["games"][0].update(changed)
    result = operation(sources=[source], generated="2026-09-15T13:00:00+00:00")
    assert not result["catalog"][0]["eligible"]
    assert not result["games"][0]["evaluations"]
    assert result["games"][0]["home"] == source["games"][0]["home"]


def test_postponement_requires_new_prospective_forecast():
    original = forecast()
    delayed = snapshot(observed="2026-09-13T12:00:00+00:00")
    delayed["games"][0]["phase"] = "POSTPONED"
    blocked = operation([original], [delayed])
    assert blocked["games"][0]["status"] == "postponed"
    assert blocked["games"][0]["final_forecast_id"] is None
    moved = snapshot(observed="2026-09-14T12:00:00+00:00")
    moved["games"][0].update(day="2026-09-15", kickoff="2026-09-15T17:00:00+00:00")
    fresh = forecast(moved, "2026-09-14T13:00:00+00:00")
    finished = finals(moved, observed="2026-09-15T23:00:00+00:00")
    result = operation([original, fresh], [finished], "2026-09-16T03:00:00+00:00")
    assert result["metrics"]["primary"]["count"] == 1
    assert result["metrics"]["all_snapshots"]["count"] == 1


@pytest.mark.parametrize("phase,expected", [("", "scheduled"), ("POSTPONED", "postponed"), ("SUSPENDED", "postponed"), ("CANCELED", "canceled"), ("CANCELLED", "canceled"), ("HALFTIME", "in_progress"), ("IN_PROGRESS", "in_progress"), ("1", "in_progress"), ("FINAL", "completed"), ("FINAL OVERTIME", "completed"), ("WHATEVER", "unknown")])
def test_status_normalization(phase, expected):
    game = scheduled()
    game.update(phase=phase, validated=True, home_score=10, away_score=7)
    observation = BEFORE if phase == "" else AFTER
    assert status(game, observation) == expected


def test_passed_kickoff_with_only_scheduled_status_is_unknown():
    assert status(scheduled(), BEFORE, AFTER) == "unknown"
    result = operation(sources=[snapshot()])
    assert result["games"][0]["status"] == "unknown"
    assert result["games"][0]["result"] is None


@pytest.mark.parametrize("change", [{"validated": False}, {"home_score": None}, {"away_score": None}, {"home_score": True}, {"home_score": -1}, {"kickoff": None}, {"day": None}, {"phase": "IN_PROGRESS"}])
def test_invalid_or_in_progress_final_never_scores(change):
    source = finals()
    source["games"][0].update(change)
    result = operation(sources=[source])
    assert result["metrics"]["primary"]["count"] == 0
    assert result["games"][0]["result"] is None


def test_final_observed_before_kickoff_is_not_completed():
    source = finals(observed="2026-09-13T16:00:00+00:00")
    result = operation(sources=[source])
    assert result["games"][0]["status"] == "unknown"
    assert result["games"][0]["result"] is None


def test_tie_excluded_from_binary_metrics_but_recorded():
    result = operation(sources=[finals(home_score=20, away_score=20)])
    assert result["games"][0]["result"]["tie"]
    assert not result["games"][0]["evaluations"]
    assert result["metrics"]["primary"]["ties_excluded"] == 1
    assert result["metrics"]["primary"]["count"] == 0
    assert "tied" in result["games"][0]["analysis"]["facts"][1]["text"]


def test_result_corrections_version_without_mutating_previous_artifacts(tmp_path):
    old_source = finals()
    old = operation(sources=[old_source])
    first = publish_operations(old, tmp_path)
    old_bytes = first.read_bytes()
    corrected = finals(home_score=10, away_score=20, observed="2026-09-14T12:00:00+00:00")
    revised = operation(sources=[old_source, corrected], generated="2026-09-14T13:00:00+00:00")
    second = publish_operations(revised, tmp_path)
    assert first != second and first.read_bytes() == old_bytes
    assert old["games"][0]["result"]["version"] != revised["games"][0]["result"]["version"]
    assert old["games"][0]["evaluations"][0]["correct"] is not revised["games"][0]["evaluations"][0]["correct"]
    assert revised["games"][0]["result"]["observed_at"] == corrected["retrieved_at"]


def test_same_result_keeps_first_observation_proof():
    first = finals()
    second = finals(observed="2026-09-14T12:00:00+00:00")
    result = operation(sources=[second, first], generated="2026-09-14T13:00:00+00:00")
    assert result["games"][0]["result"]["observed_at"] == first["retrieved_at"]
    conflicting = finals(home_score=30)
    with pytest.raises(ValueError, match="Conflicting"):
        operation(sources=[first, conflicting])


def test_duplicates_and_invalid_hashes_fail_closed():
    f = forecast()
    with pytest.raises(ValueError, match="Duplicate forecast artifact"):
        build_operations([bundle(f), bundle(f)], [finals()], AFTER)
    b = bundle(f)
    b["sha256"] = "0"*64
    with pytest.raises(ValueError, match="content address"):
        build_operations([b], [finals()], AFTER)
    f["games"].append(copy.deepcopy(f["games"][0]))
    with pytest.raises(ValueError, match="Duplicate forecast game"):
        operation([f])


def test_same_prediction_repackaged_not_double_counted():
    f = forecast()
    duplicate = copy.deepcopy(f)
    duplicate["pipeline_sha256"]["ml/current.py"] = "b"*64
    result = operation([f, duplicate])
    assert len(result["catalog"]) == 2
    assert sum(r["eligible"] for r in result["catalog"]) == 1
    assert result["metrics"]["all_snapshots"]["count"] == 1


def test_unavailable_and_cancelled_forecasts_preserved_without_scores():
    source = snapshot()
    source["games"][0]["kickoff"] = None
    unavailable = forecast(source)
    result = operation([unavailable], [finals()])
    assert len(result["catalog"]) == 1 and not result["catalog"][0]["eligible"]
    CAPTURES.clear()
    canceled = snapshot(observed="2026-09-13T12:00:00+00:00")
    canceled["games"][0]["phase"] = "CANCELLED"
    result = operation(sources=[canceled])
    assert result["games"][0]["status"] == "canceled" and not result["games"][0]["evaluations"]


@pytest.mark.parametrize("season", [2024, 2025, 2023])
def test_protected_seasons_cannot_be_reconciled(season):
    source = finals()
    source["season"] = season
    with pytest.raises(ValueError, match="Protected"):
        operation(sources=[source])


def test_cross_season_and_unknown_game_identity_not_silently_matched():
    source = finals()
    source["games"][0]["season"] = 2025
    with pytest.raises(ValueError, match="Mixed/protected"):
        operation(sources=[source])
    source = finals()
    source["games"][0]["id"] = "ngs-2026-other"
    result = operation(sources=[source])
    assert result["games"][0]["status"] == "unknown"
    assert not result["games"][0]["evaluations"]


def test_forecast_probability_coefficients_and_future_history_cannot_be_tampered():
    f = forecast()
    f["games"][0]["home_probability"] = .9
    with pytest.raises(ValueError, match="probability"):
        operation([f])
    f = forecast()
    f["model"]["intercept"] += 1
    with pytest.raises(ValueError, match="frozen"):
        operation([f])
    f = forecast()
    f["games"][0]["history"]["home"] = [{"id": "ngs-2026-future", "game_day": "2026-09-13", "observed_at": AFTER, "snapshot_sha256": "a"*64}]
    result = operation([f])
    assert not result["catalog"][0]["eligible"]
    assert result["metrics"]["primary"]["count"] == 0


def test_every_completed_game_evaluated_no_upset_selection():
    source = snapshot([scheduled(), scheduled("2", "KC", "BUF")])
    results = finals(source)
    results["games"][1].update(home_score=7, away_score=35)
    result = operation([forecast(source)], [results])
    assert len(result["games"]) == 2
    assert all(g["analysis"] for g in result["games"])
    assert result["metrics"]["primary"]["count"] == 2
    assert result["metrics"]["primary"]["accuracy"] == .5
    assert result["metrics"]["primary"]["by_season"][0]["season"] == 2026
    assert all(not g["analysis"]["deficiencies"] for g in result["games"])


def test_metric_extremes_and_calibration_are_defined():
    assert binary_score(.5, 1)["correct"]
    assert not binary_score(.5, 0)["correct"]
    assert math.isfinite(binary_score(0, 1)["log_loss"])
    assert binary_score(1, 0)["brier"] == 1
    empty = metric_set([], 0)
    assert empty["accuracy"] is None and len(empty["calibration"]) == 10


def test_source_outage_never_promotes_or_invents_new_receipt(tmp_path):
    target = publish_operations(operation(), tmp_path)
    pointer = (tmp_path / "latest.json").read_bytes()
    with pytest.raises(ValueError, match="Source unavailable"):
        build_operations([bundle(forecast())], [], AFTER)
    assert (tmp_path / "latest.json").read_bytes() == pointer and target.exists()
    stale = operation(sources=[snapshot()], generated="2026-09-18T12:00:00+00:00")
    assert any("48 hours" in warning for warning in stale["warnings"])
    assert stale["source"]["retrieved_at"] == snapshot()["retrieved_at"]
    assert stale["metrics"]["primary"]["count"] == 0


def test_publication_reproduction_integrity_and_forecast_bytes_unchanged(tmp_path):
    forecasts, operations = tmp_path / "forecasts", tmp_path / "operations"
    original = publish_local(forecast(), forecasts)
    before = original.read_bytes()
    first = export_operations(finals(), forecast_directory=forecasts, output_directory=operations, generated_at=AFTER, prior_snapshots=[snapshot()])
    second = export_operations(finals(), forecast_directory=forecasts, output_directory=operations, generated_at=AFTER, prior_snapshots=[snapshot()])
    assert first == second and original.read_bytes() == before
    pointer = json.loads((operations / "latest.json").read_bytes())
    assert pointer["sha256"] == sha(first.read_bytes())
    original.write_bytes(before + b" ")
    with pytest.raises(ValueError, match="checksum"):
        export_operations(finals(), forecast_directory=forecasts, output_directory=operations, generated_at=AFTER, prior_snapshots=[snapshot()])
    assert json.loads((operations / "latest.json").read_bytes()) == pointer


def test_missing_original_capture_preserves_receipt_but_excludes_scoring():
    result = build_operations([bundle(forecast())], [finals()], AFTER)
    assert len(result["catalog"]) == 1
    assert not result["catalog"][0]["eligible"]
    assert any("Original input snapshot unavailable" in r for r in result["catalog"][0]["exclusions"])
    assert result["metrics"]["primary"]["count"] == 0


def test_rehashed_feature_and_probability_tampering_cannot_pass_source_reproduction():
    f = forecast()
    g = f["games"][0]
    g["features"]["margin_diff"] = 9
    factor = next(r for r in g["factors"] if r["key"] == "margin_diff")
    factor.update(home=9, away=0, difference=9, contribution=9*factor["coefficient"])
    z = f["model"]["intercept"] + sum(r["contribution"] for r in g["factors"])
    g["home_probability"] = 1/(1+math.exp(-z))
    g["away_probability"] = 1-g["home_probability"]
    result = operation([f])
    assert not result["catalog"][0]["eligible"]
    assert any("does not reproduce" in r for r in result["catalog"][0]["exclusions"])
    assert not result["games"][0]["evaluations"]


def test_factor_explanation_tampering_is_rejected():
    f = forecast()
    f["games"][0]["factors"][0]["contribution"] = 1
    with pytest.raises(ValueError, match="factor explanation"):
        operation([f])


def test_protocol_hash_is_resolvable_for_archived_evaluations():
    from ml.data import ROOT
    for path in (ROOT / "web/public/data/operations").glob("operations-*.json"):
        artifact = json.loads(path.read_bytes())
        protocol = ROOT / "docs/protocols" / f"{artifact['protocol']['sha256']}.md"
        assert protocol.exists() and sha(protocol.read_bytes()) == artifact["protocol"]["sha256"]
