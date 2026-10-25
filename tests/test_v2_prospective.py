"""No real 2024/2025 data, fitting, network or production writes in these tests."""
import copy
import csv
import io
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ml.current_source import DOWNLOAD, EASTERN, canonical, iso, normalize, sha, timestamp
from ml.data import ROOT, load_snapshot
from ml.v2_data import COLUMNS, load_inputs
from ml.v2_features import FEATURES, build_features
from ml.v2_prospective import (MODEL_SHA, PBP_LICENSE, PBP_URL, SCHEDULE_LICENSE,
                              _pbp_totals, _prior_scores, feature_state, frozen_v2,
                              plan, probability, readiness, run, simulate, verify_capture)
from ml.v2_shadow_store import read, write

GENERATED = "2026-09-27T16:05:00+00:00"


def csv_bytes(rows):
    output = io.StringIO(); writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader(); writer.writerows(rows)
    return output.getvalue().encode()


def game(key, season, week, day, home, away, hs="", aws="", phase="SCHEDULED"):
    return dict(season=str(season), season_type="REG", week=str(week), game_key=str(key),
                game_id=f"fixture-{season}-{key}", game_time=f"{day}T17:00:00Z", game_date="",
                phase=phase, home_team_abbr=home, visitor_team_abbr=away, home_score=str(hs),
                visitor_score=str(aws), validated="true", site_full_name="Synthetic test venue")


def fixture():
    schedules = [game(100, 2026, 1, "2026-09-13", "DET", "GB", 21, 7, "FINAL"),
                 game(101, 2026, 2, "2026-09-20", "GB", "CHI", 10, 20, "FINAL"),
                 game(102, 2026, 3, "2026-09-27", "DET", "GB")]
    priors = [game(10, 2025, 1, "2025-09-07", "DET", "GB", 14, 7, "FINAL")]
    plays = []
    for g, yards in zip(schedules[:2], [(6, 4), (5, 7)]):
        for side, own, other, y in [(0, g["home_team_abbr"], g["visitor_team_abbr"], yards[0]),
                                     (1, g["visitor_team_abbr"], g["home_team_abbr"], yards[1])]:
            plays.append(dict(season=2026, season_type="REG",
                game_id=f"2026_{int(g['week']):02d}_{g['visitor_team_abbr']}_{g['home_team_abbr']}",
                play_id=side+1, posteam=own, defteam=other, play_type="run", yards_gained=float(y),
                qb_kneel=0, qb_spike=0, two_point_attempt=0, week=int(g["week"]),
                home_team=g["home_team_abbr"], away_team=g["visitor_team_abbr"], game_date=g["game_time"][:10]))
    bodies = dict(schedule=csv_bytes(schedules), prior=csv_bytes(priors), pbp=pd.DataFrame(plays).to_parquet(index=False))
    captures = {}
    for kind, raw in bodies.items():
        season = 2025 if kind == "prior" else 2026
        captures[kind] = (raw, dict(kind=kind, season=season, synthetic=True,
            url=PBP_URL if kind == "pbp" else f"{DOWNLOAD}/ngs_schedule_{season}.csv",
            license_url=PBP_LICENSE if kind == "pbp" else SCHEDULE_LICENSE,
            raw_sha256=sha(raw), retrieved_at="2026-09-27T15:30:00Z",
            source_updated_at="2026-09-21T04:00:00Z" if kind == "pbp" else "2026-09-27T15:00:00Z"))
    return captures


def changed(captures, kind, raw):
    captures = copy.deepcopy(captures)
    captures[kind] = (raw, dict(captures[kind][1], raw_sha256=sha(raw)))
    return captures


def schedule_rows(captures, kind="schedule"):
    return list(csv.DictReader(io.StringIO(captures[kind][0].decode())))


def test_disabled_before_any_input_open(monkeypatch):
    assert readiness()["enabled"] is False
    assert plan()["enabled"] is False and plan()["activation_at"] is None
    assert plan()["prior_2025_use_approved"] is True
    assert plan()["activation_approved"] is False
    monkeypatch.setattr(Path, "read_bytes", lambda *_: pytest.fail("Input must not be opened"))
    with pytest.raises(PermissionError, match="disabled"):
        run(Path("protected-2025-inputs-must-not-be-read.json"))
    with pytest.raises(PermissionError):
        verify_capture(b"must-not-parse", {}, "prior", timestamp(GENERATED))


def test_saved_model_hash_no_scaler_refit_or_double_scaling():
    model = frozen_v2()
    assert sha(canonical(model)) == MODEL_SHA
    assert model["fit_seasons"] == [2011, 2021] and model["calibration"]["season"] == 2022
    features = dict(zip(FEATURES, [.2, 3., -2., 7., 1.3, .3, -.4], strict=True))
    z = model["intercept"] + sum(c*features[f] for c, f in zip(model["coefficients"], FEATURES))
    expected = 1/(1+np.exp(-(model["calibration"]["intercept"] + model["calibration"]["coefficient"]*z)))
    assert probability(features) == expected


def test_saved_2023_probabilities_reproduce_without_fitting():
    from ml.data import ROOT
    from ml.v2_prospective import RESULT_SHA
    saved = json.loads((ROOT/f"research/v2/result-{RESULT_SHA}.json").read_bytes())
    rows = [r for r in saved["predictions"] if r["season"] == 2023]
    assert len(rows) == 272
    np.testing.assert_allclose([probability(r["features"]) for r in rows],
                               [r["probabilities"]["v2"] for r in rows], atol=2e-15, rtol=0)
    missing = dict(rows[0]["features"]); missing.pop(FEATURES[-1])
    with pytest.raises(ValueError, match="Missing/nonfinite"): probability(missing)


def test_full_synthetic_adapter_reproducible_and_honest_timestamps():
    captures = fixture()
    first = simulate(captures, "ngs-2026-102", GENERATED)
    assert first["status"] == "available" and first["prospective"] is False
    assert len(first["features"]) == 7 and len(first["joins"]) == 2
    assert first["source_age_hours"]["pbp"] > 48  # Source publication is not retrieval time.
    assert first["sources"][1]["retrieved_at"] != first["sources"][1]["source_updated_at"]
    assert canonical(first) == canonical(simulate(captures, "ngs-2026-102", GENERATED))
    assert first["history"]["home"]["prior_ids"] == ["ngs-2025-10"]


@pytest.mark.parametrize("kind", ["schedule", "pbp", "prior"])
@pytest.mark.parametrize("field,value", [("raw_sha256", "0"*64), ("season", 2024),
    ("url", "https://example.com/untrusted"), ("retrieved_at", "2026-09-27T16:00:00Z"),
    ("source_updated_at", "2026-09-28T00:00:00Z"), ("synthetic", False)])
def test_provenance_and_cutoff_rejection(kind, field, value):
    captures = fixture(); captures[kind][1][field] = value
    with pytest.raises(ValueError): simulate(captures, "ngs-2026-102", GENERATED)


@pytest.mark.parametrize("generated", ["2026-09-27T15:59:59Z", "2026-09-27T17:00:00Z", "2026-09-27T18:00:00Z"])
def test_generation_not_backdated_or_after_kickoff(generated):
    with pytest.raises(ValueError, match="Generation"):
        simulate(fixture(), "ngs-2026-102", generated)


def test_old_capture_not_mislabeled_current():
    captures = fixture()
    captures["pbp"][1]["retrieved_at"] = "2026-09-27T09:59:59Z"
    with pytest.raises(ValueError, match="six-hour"):
        simulate(captures, "ngs-2026-102", GENERATED)


def test_protected_or_mixed_parquet_rejected_before_football_columns():
    captures = fixture()
    for years in [[2025], [2024, 2026]]:
        # Deliberately no football columns, let alone real protected outcomes.
        raw = pd.DataFrame({"season": years}).to_parquet(index=False)
        with pytest.raises(ValueError, match="protected/mixed"):
            simulate(changed(captures, "pbp", raw), "ngs-2026-102", GENERATED)


def test_missing_prior_never_substitutes_zero_or_2023():
    captures = fixture(); rows = schedule_rows(captures, "prior")
    rows[0]["visitor_team_abbr"] = "CHI"
    record = simulate(changed(captures, "prior", csv_bytes(rows)), "ngs-2026-102", GENERATED)
    assert record["status"] == "unavailable" and record["home_probability"] is None
    rows[0]["season"] = "2023"
    with pytest.raises(ValueError, match="only 2025"):
        simulate(changed(captures, "prior", csv_bytes(rows)), "ngs-2026-102", GENERATED)


def test_missing_efficiency_and_postponed_intervening_game_fail_closed():
    captures = fixture(); pbp = pd.read_parquet(io.BytesIO(captures["pbp"][0]))
    missing = pbp[pbp.week.eq(2)].to_parquet(index=False)
    record = simulate(changed(captures, "pbp", missing), "ngs-2026-102", GENERATED)
    assert record["status"] == "unavailable" and record["features"] == {}
    rows = schedule_rows(captures); rows[1]["phase"] = "POSTPONED"
    record = simulate(changed(captures, "schedule", csv_bytes(rows)), "ngs-2026-102", GENERATED)
    assert record["status"] == "unavailable"


@pytest.mark.parametrize("mutation", ["identity", "duplicate", "missing-flag", "missing-yards"])
def test_invalid_pbp_not_silently_imputed(mutation):
    captures = fixture(); pbp = pd.read_parquet(io.BytesIO(captures["pbp"][0]))
    if mutation == "identity": pbp.loc[0, "home_team"] = "KC"
    elif mutation == "duplicate": pbp = pd.concat([pbp, pbp.iloc[[0]]])
    elif mutation == "missing-flag": pbp.loc[0, "qb_kneel"] = None
    else: pbp.loc[0, "yards_gained"] = np.nan
    with pytest.raises(ValueError):
        simulate(changed(captures, "pbp", pbp.to_parquet(index=False)), "ngs-2026-102", GENERATED)


def test_scrimmage_filters_equal_frozen_definition():
    captures = fixture(); pbp = pd.read_parquet(io.BytesIO(captures["pbp"][0]))
    extra = []
    for i, (typ, flag) in enumerate([("run", "qb_kneel"), ("pass", "qb_spike"),
                                   ("run", "two_point_attempt"), ("no_play", None)]):
        row = pbp.iloc[0].to_dict(); row.update(play_id=100+i, play_type=typ, yards_gained=90.)
        if flag: row[flag] = 1
        extra.append(row)
    modified = pd.concat([pbp, pd.DataFrame(extra)]).to_parquet(index=False)
    before = simulate(captures, "ngs-2026-102", GENERATED)
    after = simulate(changed(captures, "pbp", modified), "ngs-2026-102", GENERATED)
    assert before["features"] == after["features"] and before["home_probability"] == after["home_probability"]


def test_week_one_and_bye_preserve_frozen_priors():
    captures = fixture(); rows = schedule_rows(captures)
    rows = [rows[-1]]; rows[0]["week"] = "1"
    # A future-game PBP row suffices to verify the season; no past plays are required in Week 1.
    pbp = pd.read_parquet(io.BytesIO(captures["pbp"][0])).iloc[:1].copy(); pbp["game_date"] = "2026-10-04"
    modified = changed(changed(captures, "schedule", csv_bytes(rows)), "pbp", pbp.to_parquet(index=False))
    record = simulate(modified, "ngs-2026-102", GENERATED)
    assert record["status"] == "available"
    assert [record["features"][f] for f in FEATURES[:4]] == [0., 0., 0., 0.]
    assert record["features"]["prior_margin_diff"] == 14/5
    assert record["features"]["adjusted_offense_ypp_diff"] == 0
    # Original DET last played 14 days ago, GB seven: preserve clipped rest difference.
    assert simulate(captures, "ngs-2026-102", GENERATED)["features"]["rest_diff"] == 7


def test_future_same_day_and_opponent_later_games_cannot_enter_features():
    captures = fixture(); before = simulate(captures, "ngs-2026-102", GENERATED)
    rows = schedule_rows(captures)
    rows.extend([game(103, 2026, 4, "2026-10-04", "CHI", "DET", 99, 0, "FINAL"),
                 game(104, 2026, 3, "2026-09-27", "GB", "KC", 99, 0, "FINAL")])
    rows[-1]["game_time"] = "2026-09-27T13:00:00Z"
    after = simulate(changed(captures, "schedule", csv_bytes(rows)), "ngs-2026-102", GENERATED)
    assert before["features"] == after["features"]
    for side in after["history"].values():
        assert all(day < "2026-09-27" for day in side["dates"])
        for entry in side["efficiency"]:
            assert all(day < entry["gameday"] for day in entry["opponent_history_dates"])


def test_opponents_later_pregame_result_does_not_rewrite_earlier_adjustment():
    captures = fixture(); before = simulate(captures, "ngs-2026-102", GENERATED)
    rows = schedule_rows(captures)
    rows.append(game(103, 2026, 3, "2026-09-24", "CHI", "KC", 99, 0, "FINAL"))
    pbp = pd.read_parquet(io.BytesIO(captures["pbp"][0]))
    extra = []
    for own, opponent, yards in [("CHI", "KC", 90.), ("KC", "CHI", -20.)]:
        row = pbp.iloc[0].to_dict()
        row.update(game_id="2026_03_KC_CHI", play_id=len(extra)+1, home_team="CHI", away_team="KC",
                   posteam=own, defteam=opponent, yards_gained=yards, week=3, game_date="2026-09-24")
        extra.append(row)
    modified = changed(changed(captures, "schedule", csv_bytes(rows)), "pbp", pd.concat([pbp, pd.DataFrame(extra)]).to_parquet(index=False))
    after = simulate(modified, "ngs-2026-102", GENERATED)
    assert before["features"] == after["features"]


def test_live_coverage_checks_reject_incomplete_seasons():
    captures = fixture()
    with pytest.raises(ValueError, match="Incomplete"):
        normalize(captures["schedule"][0], 2026)
    with pytest.raises(ValueError, match="Incomplete prior"):
        _prior_scores(captures["prior"][0])
    # No football fields are needed to reject a protected/mixed season.
    with pytest.raises(ValueError, match="only 2025"):
        _prior_scores(b"season\n2024\n")


@pytest.mark.parametrize("phase", ["POSTPONED", "SUSPENDED", "FINAL"])
def test_unscheduled_target_unavailable(phase):
    captures = fixture(); rows = schedule_rows(captures); rows[-1]["phase"] = phase
    assert simulate(changed(captures, "schedule", csv_bytes(rows)), "ngs-2026-102", GENERATED)["status"] == "unavailable"


def test_unconfirmed_and_rescheduled_kickoff_not_reused():
    captures = fixture(); rows = schedule_rows(captures); rows[-1]["game_time"] = ""
    with pytest.raises(ValueError, match="unconfirmed"):
        simulate(changed(captures, "schedule", csv_bytes(rows)), "ngs-2026-102", GENERATED)
    rows[-1]["game_time"] = "2026-09-28T00:00:00Z"
    with pytest.raises(ValueError, match="Generation"):
        simulate(changed(captures, "schedule", csv_bytes(rows)), "ngs-2026-102", GENERATED)


def test_observation_exactly_at_cutoff_is_unavailable_in_kernel():
    captures = fixture(); games = normalize(captures["schedule"][0], 2026, full_coverage=False)
    for g in games: g["observed_at"] = "2026-09-27T16:00:00Z"
    priors = _prior_scores(captures["prior"][0], full_coverage=False)
    totals, _ = _pbp_totals(captures["pbp"][0], games, "2026-09-27")
    with pytest.raises(ValueError, match="Missing required"):
        feature_state(games[-1], games, totals, priors, timestamp("2026-09-27T16:00:00Z"))


@pytest.mark.skipif(not (ROOT / "data/schedules-2010-2023.csv").exists(), reason="Approved local raw inputs unavailable; no CI downloads")
def test_feature_adapter_parity_with_authorized_2023_research():
    games, _ = load_snapshot(); totals, _ = load_inputs()
    historical = build_features(games, totals)
    games = games[games.game_type.eq("REG")]
    def convert(row):
        kickoff = datetime.fromisoformat(f"{row.gameday}T{row.gametime}").replace(tzinfo=EASTERN)
        return dict(id=row.game_id, season=int(row.season), week=int(row.week), home=row.home_team,
                    away=row.away_team, day=row.gameday, kickoff=iso(kickoff), phase="FINAL", validated=True,
                    home_score=int(row.home_score), away_score=int(row.away_score), observed_at="2023-01-01T00:00:00Z")
    current = [convert(r) for r in games[games.season.eq(2023)].itertuples()]
    priors = [convert(r) for r in games[games.season.eq(2022)].itertuples()]
    lookup = {(r["game_id"], r["team"]): r for r in totals[totals.season.eq(2023)].to_dict("records")}
    selected = historical[historical.season.eq(2023) & historical.week.isin([1, 2, 7, 18])]
    for row in selected.itertuples():
        target = dict(next(g for g in current if g["id"] == row.game_id), phase="SCHEDULED")
        cutoff = timestamp(target["kickoff"]) - timedelta(hours=1)
        features, _ = feature_state(target, current, lookup, priors, cutoff)
        np.testing.assert_allclose([features[f] for f in FEATURES], [getattr(row, f) for f in FEATURES], atol=1e-14, rtol=0)


def test_immutable_atomic_shadow_is_separate_reproducible_and_concurrent(tmp_path):
    record = simulate(fixture(), "ngs-2026-102", GENERATED)
    with ThreadPoolExecutor(max_workers=4) as pool:
        receipts = list(pool.map(lambda _: write(record, tmp_path), range(8)))
    assert all(r == receipts[0] for r in receipts)
    assert read(receipts[0]) == record
    assert len(list(tmp_path.rglob("*.json"))) == 1
    modified = dict(record, generated_at="2026-09-27T16:06:00+00:00")
    with pytest.raises(ValueError, match="Immutable decision conflict"): write(modified, tmp_path)
    assert read(receipts[0])["generated_at"] == record["generated_at"]
    assert not list(tmp_path.rglob(".pending-*"))


def test_no_live_or_public_writes_and_no_probability_tampering(tmp_path):
    record = simulate(fixture(), "ngs-2026-102", GENERATED)
    with pytest.raises(PermissionError): write(dict(record, mode="v2-shadow-forecast", prospective=True), tmp_path)
    with pytest.raises(ValueError, match="isolated"):
        write(record, Path(__file__).resolve().parents[1]/"web/public/data/v2")
    with pytest.raises(ValueError, match="probability"):
        write(dict(record, home_probability=.99), tmp_path)
    receipt = write(record, tmp_path)
    Path(receipt["file"]).write_text("tampered")
    with pytest.raises(ValueError, match="checksum"): read(receipt)


def test_interrupted_write_never_publishes_partial_record(tmp_path, monkeypatch):
    import ml.v2_shadow_store as store
    def fail(*args, **kwargs): raise OSError("simulated interrupted publication")
    monkeypatch.setattr(store.os, "link", fail)
    with pytest.raises(OSError): write(simulate(fixture(), "ngs-2026-102", GENERATED), tmp_path)
    assert not list(tmp_path.rglob("*.json")) and not list(tmp_path.rglob(".pending-*"))
