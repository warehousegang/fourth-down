"""RC1 synthetic lifecycle validation. Never writes production data or forecasts."""
import argparse
import copy
import json
import math
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from ml.data import ROOT
from ml.current import MODEL_FREEZE_SHA, frozen_model, generate, publish_local
from ml.current_source import canonical, sha
from ml.intelligence import eligible_evidence
from ml.lifecycle import build_operations, publish_operations

VIRTUAL_PREGAME = "2026-10-03T12:00:00+00:00"
VIRTUAL_POSTGAME = "2026-10-05T00:00:00+00:00"
CASES = (
    ("strong_favorite_loses", "A model-derived strong home favorite loses a controlled synthetic game."),
    ("underdog_wins", "A model-derived home underdog beats the strong away favorite."),
    ("correct_favorite", "The model-derived strong home favorite wins."),
    ("missing_final", "Kickoff passed, but no verified final result is available."),
    ("postponed", "An explicitly postponed game remains unscored."),
    ("corrected_final", "A later score correction creates a new result/evaluation version."),
    ("late_injury_context", "A synthetic injury report after cutoff is rejected and cannot change the forecast."),
    ("stale_source", "A stale source yields an unavailable forecast without an invented probability."),
    ("missing_source", "A reconciliation source outage preserves the prior immutable evidence and pointer."),
    ("missing_feature_input", "An incomplete earlier result blocks a probability and postgame scoring."),
    ("duplicate_events", "Repeated identical result receipts and reconciliation are idempotent."),
    ("failed_generation", "Invalid source timing fails generation without changing an existing forecast."),
    ("in_progress", "A game observed in progress does not acquire a fabricated final score."),
    ("tied_final", "A verified synthetic tie is recorded and excluded from binary scores."),
)


def synthetic_source(case_id, advantage=1):
    """Fixed test histories, never real NFL statistics; four earlier 20-point margins."""
    games = []
    for index in range(4):
        day = date(2026, 9, 6) + timedelta(days=7*index)
        games.append({"id": f"ngs-2026-synthetic-{case_id}-history-{index+1}", "source_game_id": f"synthetic-{index+1}",
            "season": 2026, "week": index+1, "home": "DET", "away": "GB", "day": str(day),
            "kickoff": f"{day}T17:00:00+00:00", "home_score": 30 if advantage > 0 else 10,
            "away_score": 10 if advantage > 0 else 30, "phase": "FINAL", "validated": True,
            "stadium": "SYNTHETIC TEST VENUE — NOT AN NFL FIXTURE"})
    games.append({"id": f"ngs-2026-synthetic-{case_id}-target", "source_game_id": "synthetic-target", "season": 2026,
        "week": 5, "home": "DET", "away": "GB", "day": "2026-10-04", "kickoff": "2026-10-04T17:00:00+00:00",
        "home_score": None, "away_score": None, "phase": "", "validated": False,
        "stadium": "SYNTHETIC TEST VENUE — NOT AN NFL FIXTURE"})
    return {"schema_version": 1, "season": 2026, "synthetic": True,
            "retrieved_at": "2026-10-03T11:00:00+00:00", "source_updated_at": "2026-10-03T10:00:00+00:00",
            "source_url": f"https://example.invalid/fourth-down/synthetic/{case_id}/2026",
            "raw_sha256": sha(canonical(games)), "asset_id": 0,
            "source_name": "SYNTHETIC RC1 FIXTURE — NOT OBSERVED NFL DATA",
            "license_url": "https://example.invalid/synthetic-no-external-data", "games": games}


def result_source(source, phase="FINAL", home_score=30, away_score=10, observed="2026-10-04T22:00:00+00:00"):
    result = copy.deepcopy(source)
    result["retrieved_at"] = result["source_updated_at"] = observed
    result["games"][-1].update(phase=phase, validated=phase in {"FINAL", "FINAL OVERTIME"},
                               home_score=home_score, away_score=away_score)
    result["raw_sha256"] = sha(canonical(result["games"]))
    return result


def checked(checks, label, condition):
    if not condition:
        raise AssertionError("Synthetic lifecycle verification failed: " + label)
    checks[label] = True


def artifact_record(path, kind):
    body = path.read_bytes()
    return {"kind": kind, "file": path.name, "sha256": sha(body), "payload": json.loads(body)}


def expected_score(probability, outcome):
    """Independent scalar oracle; does not call lifecycle scoring/aggregation helpers."""
    observed = probability if outcome else 1-probability
    return {"correct": (probability >= .5) == bool(outcome), "brier": (probability-outcome)**2,
            "log_loss": -math.log(observed), "surprise": -math.log(observed)}


def verify_operations(operations, checks):
    scores = []
    for game in operations["games"]:
        if game["analysis"]:
            facts = game["analysis"]["facts"]
            checked(checks, "facts_have_sources_and_observation_times", all(f["source_url"].startswith("https://example.invalid/") and f["observed_at"] for f in facts))
            checked(checks, "no_single_game_model_defect_claim", game["analysis"]["deficiencies"] == [])
            checked(checks, "no_injury_weather_or_qb_cause_in_verified_facts", all(not any(term in f["text"].lower() for term in ("injur", "weather", "quarterback", "caused", "because")) for f in facts))
            checked(checks, "hypotheses_require_missing_evidence", all(h["evidence_needed"] for h in game["analysis"]["hypotheses"]))
            checked(checks, "no_paid_or_probabilistic_agent_action", game["analysis"]["agent_boundary"]["paid_calls"] == 0 and "modify probabilities" in game["analysis"]["agent_boundary"]["forbidden_actions"])
        for score in game["evaluations"]:
            oracle = expected_score(score["home_probability"], score["outcome_home"])
            checked(checks, "independent_per_game_accuracy", score["correct"] == oracle["correct"])
            for key in ("brier", "log_loss", "surprise"):
                checked(checks, "independent_"+key, abs(score[key]-oracle[key]) < 1e-12)
            scores.append(score)
    for name, rows in (("all_snapshots", scores), ("primary", [r for r in scores if r["primary"]])):
        metrics = operations["metrics"][name]
        checked(checks, name+"_population", metrics["count"] == len(rows))
        checked(checks, name+"_calibration_population", sum(b["count"] for b in metrics["calibration"]) == len(rows))
        for key in ("brier", "log_loss"):
            expected = sum(r[key] for r in rows)/len(rows) if rows else None
            checked(checks, name+"_"+key, metrics[key] is None if expected is None else abs(metrics[key]-expected) < 1e-12)


def run_case(case_id, description, temporary_root):
    checks, records, failures, annotation = {}, [], [], None
    source = synthetic_source(case_id, -1 if case_id == "underdog_wins" else 1)
    if case_id == "stale_source":
        source["source_updated_at"] = "2026-09-29T10:00:00+00:00"
    if case_id == "missing_feature_input":
        source["games"][0]["home_score"] = None
        source["raw_sha256"] = sha(canonical(source["games"]))
    current_directory, operations_directory = temporary_root / case_id / "current", temporary_root / case_id / "operations"
    forecast = generate(source, [], VIRTUAL_PREGAME, VIRTUAL_PREGAME)
    checked(checks, "frozen_incumbent_unchanged", forecast["model"] == frozen_model() and forecast["model_freeze_sha256"] == MODEL_FREEZE_SHA)
    checked(checks, "exactly_one_synthetic_upcoming_game", len(forecast["games"]) == 1 and "synthetic-" in forecast["games"][0]["id"])
    target = forecast["games"][0]
    probability = target["home_probability"]
    if probability is not None:
        z = forecast["model"]["intercept"] + sum(target["features"][feature]*coefficient for feature,coefficient in zip(forecast["model"]["features"], forecast["model"]["coefficients"], strict=True))
        checked(checks, "probability_derived_from_frozen_coefficients", abs(probability-1/(1+math.exp(-z))) < 1e-12)
        checked(checks, "strong_favorite_created_by_test_history", probability < .2 if case_id == "underdog_wins" else probability > .8)
    forecast_path = publish_local(forecast, current_directory)
    original_bytes, original_pointer = forecast_path.read_bytes(), (current_directory/"latest.json").read_bytes()
    records.append(artifact_record(forecast_path, "synthetic-forecast"))
    bundle = {"file": forecast_path.name, "sha256": sha(original_bytes), "artifact": forecast}
    snapshots = [source]
    operations = build_operations([bundle], snapshots, VIRTUAL_PREGAME)
    operations_path = publish_operations(operations, operations_directory)
    records.append(artifact_record(operations_path, "synthetic-operations"))
    initial_operations_pointer = (operations_directory/"latest.json").read_bytes()
    checked(checks, "pregame_has_zero_observed_scores", operations["metrics"]["primary"]["count"] == 0)
    statuses = [operations["games"][0]["status"]]
    initial_operations_bytes = operations_path.read_bytes()
    if case_id == "missing_source":
        try:
            build_operations([bundle], [], VIRTUAL_POSTGAME)
        except ValueError as error:
            failures.append({"stage": "reconciliation", "type": type(error).__name__, "message": str(error)})
        checked(checks, "source_outage_is_explicit", bool(failures) and "Source unavailable" in failures[-1]["message"])
        checked(checks, "source_outage_keeps_previous_pointer", (operations_directory/"latest.json").read_bytes() == initial_operations_pointer)
    elif case_id == "failed_generation":
        invalid = copy.deepcopy(source)
        invalid["retrieved_at"] = "2026-10-03T13:00:00+00:00"
        try:
            generate(invalid, [], VIRTUAL_PREGAME, VIRTUAL_PREGAME)
        except ValueError as error:
            failures.append({"stage": "generation", "type": type(error).__name__, "message": str(error)})
        checked(checks, "invalid_source_time_fails_generation", bool(failures) and "time ordering" in failures[-1]["message"])
        checked(checks, "failed_generation_creates_no_version", len(list(current_directory.glob("forecast-*.json"))) == 1)
    else:
        if case_id == "late_injury_context":
            late = {"domain": "injuries", "game_id": target["id"], "team": "DET", "season": 2026,
                    "source_url": "https://example.invalid/synthetic/injury", "source_sha256": sha(b"SYNTHETIC INJURY FIXTURE"),
                    "published_at": "2026-10-03T12:30:00+00:00", "observed_at": "2026-10-03T12:31:00+00:00",
                    "retrieved_at": "2026-10-03T12:32:00+00:00", "valid_until": "2026-10-04T18:00:00+00:00",
                    "verification": "verified", "license_reviewed": True, "phase": "pregame",
                    "value": {"availability": "out", "player_id": "synthetic-player-never-ingested"}}
            annotation = eligible_evidence([late], game_id=target["id"], team="DET", season=2026,
                                          cutoff=target["cutoff"], kickoff=target["kickoff"], approved_hosts=("example.invalid",))
            checked(checks, "late_injury_annotation_rejected", annotation["status"] == "unavailable" and bool(annotation["rejected"]))
            checked(checks, "injury_annotation_cannot_change_probability", annotation["probability_adjustment"] is None and not annotation["model_feature_enabled"])
            checked(checks, "identical_inputs_reproduce_original_after_annotation", canonical(generate(source, [], VIRTUAL_PREGAME, VIRTUAL_PREGAME)) == original_bytes)
        phase, hs, aws = "FINAL", 30, 10
        if case_id in {"strong_favorite_loses", "late_injury_context"}:
            hs, aws = 10, 30
        if case_id == "missing_final":
            phase, hs, aws = "", None, None
        if case_id == "postponed":
            phase, hs, aws = "POSTPONED", None, None
        if case_id == "in_progress":
            phase, hs, aws = "HALFTIME", 7, 10
        if case_id == "tied_final":
            hs, aws = 20, 20
        result = result_source(source, phase, hs, aws)
        snapshots.append(result)
        operations = build_operations([bundle], snapshots, VIRTUAL_POSTGAME)
        operations_path = publish_operations(operations, operations_directory)
        records.append(artifact_record(operations_path, "synthetic-operations"))
        statuses.append(operations["games"][0]["status"])
        verify_operations(operations, checks)
        if case_id == "corrected_final":
            before_correction = operations
            before_path, before_bytes = operations_path, operations_path.read_bytes()
            corrected = result_source(source, "FINAL", 10, 30, "2026-10-05T01:00:00+00:00")
            snapshots.append(corrected)
            operations = build_operations([bundle], snapshots, "2026-10-05T02:00:00+00:00")
            operations_path = publish_operations(operations, operations_directory)
            records.append(artifact_record(operations_path, "synthetic-operations"))
            statuses.append(operations["games"][0]["status"])
            checked(checks, "corrected_result_creates_distinct_version", operations["games"][0]["result"]["version"] != before_correction["games"][0]["result"]["version"] and operations_path != before_path)
            checked(checks, "previous_evaluation_bytes_preserved", before_path.read_bytes() == before_bytes)
            checked(checks, "corrected_outcome_changes_correctness", before_correction["metrics"]["primary"]["accuracy"] == 1 and operations["metrics"]["primary"]["accuracy"] == 0)
            verify_operations(operations, checks)
        if case_id == "duplicate_events":
            before_pointer, before_bytes = (operations_directory/"latest.json").read_bytes(), operations_path.read_bytes()
            repeated = build_operations([bundle], [*snapshots, copy.deepcopy(result)], VIRTUAL_POSTGAME)
            repeated_path = publish_operations(repeated, operations_directory)
            checked(checks, "duplicate_event_and_run_are_idempotent", repeated_path == operations_path and canonical(repeated) == before_bytes and (operations_directory/"latest.json").read_bytes() == before_pointer)
            checked(checks, "duplicate_events_count_game_once", repeated["metrics"]["primary"]["count"] == repeated["metrics"]["all_snapshots"]["count"] == 1)
            try:
                build_operations([bundle, bundle], snapshots, VIRTUAL_POSTGAME)
            except ValueError as error:
                failures.append({"stage": "duplicate_forecast_receipt", "type": type(error).__name__, "message": str(error)})
            checked(checks, "duplicate_receipt_rejected_without_pointer_change", bool(failures) and "Duplicate forecast artifact" in failures[-1]["message"] and (operations_directory/"latest.json").read_bytes() == before_pointer)
    row = operations["games"][0]
    expected_status = {"missing_final": "unknown", "postponed": "postponed", "in_progress": "in_progress",
                       "missing_source": "scheduled", "failed_generation": "scheduled"}.get(case_id, "completed")
    checked(checks, "expected_final_status", row["status"] == expected_status)
    unscored = {"missing_final", "postponed", "in_progress", "missing_source", "failed_generation", "stale_source", "missing_feature_input", "tied_final"}
    checked(checks, "expected_scoring_population", operations["metrics"]["primary"]["count"] == (0 if case_id in unscored else 1))
    if case_id in {"stale_source", "missing_feature_input"}:
        checked(checks, "missing_inputs_never_fabricate_probability", target["status"] == "unavailable" and probability is None and not target["features"])
    if case_id == "tied_final":
        checked(checks, "tie_retained_but_excluded", row["result"]["tie"] and operations["metrics"]["primary"]["ties_excluded"] == 1)
    if case_id in {"strong_favorite_loses", "underdog_wins"}:
        checked(checks, "upset_is_wrong_pick_not_demonstrated_defect", operations["metrics"]["primary"]["accuracy"] == 0 and row["analysis"]["deficiencies"] == [])
    if case_id == "correct_favorite":
        checked(checks, "correct_favorite_pick", operations["metrics"]["primary"]["accuracy"] == 1)
    checked(checks, "original_forecast_bytes_and_pointer_immutable", forecast_path.read_bytes() == original_bytes and (current_directory/"latest.json").read_bytes() == original_pointer)
    checked(checks, "pregame_operations_bytes_immutable", records[1]["sha256"] == sha(initial_operations_bytes) and (operations_directory/records[1]["file"]).read_bytes() == initial_operations_bytes)
    verify_operations(operations, checks)
    return {"id": case_id, "description": description, "synthetic": True, "checks": checks, "status_transitions": statuses,
            "home_probability": probability, "features": target["features"], "scored_games": operations["metrics"]["primary"]["count"],
            "final_metrics": operations["metrics"], "failures": failures, "annotation": annotation,
            "input_snapshots": snapshots, "artifacts": records}


def allowed_output(directory):
    path = Path(directory).resolve()
    repository = ROOT.resolve()
    # Repository restrictions take precedence when the entire checkout is in /tmp.
    # Keep the approved suffix literal: a symlink there must not approve its target.
    approved = repository/"artifacts/rc1/scenarios"
    if path == repository or path.is_relative_to(repository):
        if path == approved or path.is_relative_to(approved):
            return path
        raise ValueError("Synthetic output cannot target repository paths outside artifacts/rc1/scenarios")
    temporary_roots = (Path(tempfile.gettempdir()).resolve(), Path("/private/tmp").resolve())
    if not any(path == root or path.is_relative_to(root) for root in temporary_roots):
        raise ValueError("Synthetic output must stay under artifacts/rc1/scenarios or an OS temporary directory")
    return path


def run_scenarios(output_directory=None):
    output = allowed_output(output_directory or ROOT/"artifacts/rc1/scenarios")
    with tempfile.TemporaryDirectory(prefix="fourth-down-rc1-synthetic-") as temporary:
        scenarios = [run_case(identifier, description, Path(temporary)) for identifier, description in CASES]
    result = {"schema_version": 1, "mode": "synthetic-lifecycle-simulation", "synthetic": True,
              "virtual_clock": {"pregame": VIRTUAL_PREGAME, "postgame": VIRTUAL_POSTGAME},
              "real_nfl_outcomes_consumed": 0, "model_fits": 0, "network_calls": 0, "production_writes": 0,
              "model_id": frozen_model()["id"], "model_freeze_sha256": MODEL_FREEZE_SHA,
              "harness_sha256": sha((ROOT/"ml/lifecycle_simulation.py").read_bytes()),
              "scenario_count": len(scenarios), "assertion_count": sum(len(s["checks"]) for s in scenarios),
              "scenarios": scenarios,
              "limitations": ["All schedules, scores, player annotations and observation timestamps are fixed synthetic test fixtures, not observed NFL data.",
                              "Virtual pregame timestamps simulate execution order; these were never forecasts actually issued on those dates.",
                              "Probabilities are produced by the unchanged frozen model from synthetic feature states; no probability or coefficient is forced to a desired value.",
                              "Scenario pass/fail tests software behavior and arithmetic, not NFL predictive accuracy, model calibration or causal explanations.",
                              "All intermediate forecast/evaluation publications occur in a temporary directory and are removed after capture into this explicitly synthetic report."]}
    body = canonical(result); digest = sha(body)
    output.mkdir(parents=True, exist_ok=True)
    path = output/f"scenario-evidence-{digest}.json"
    if path.exists() and path.read_bytes() != body:
        raise ValueError("Synthetic evidence checksum collision")
    if not path.exists():
        with path.open("xb") as stream:
            stream.write(body)
    return {"artifact": str(path), "sha256": digest, "scenario_count": result["scenario_count"],
            "assertion_count": result["assertion_count"], "synthetic": True, "production_writes": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", help="Only artifacts/rc1/scenarios or a temporary directory is permitted")
    args = parser.parse_args()
    print(json.dumps(run_scenarios(args.output_directory), indent=2))


if __name__ == "__main__":
    main()
