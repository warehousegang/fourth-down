"""Research contracts run without fitting, fetching, or changing production."""
import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ml.challenger import canonical, frozen_model, predict, sha
from ml.data import ROOT, load_snapshot
from ml.features import FEATURES as V1_FEATURES, build_features as v1_features
from ml.v2_data import COLUMNS, DIRECTORY, aggregate, check_year, load_inputs
from ml.v2_experiment import calibration, fit_fold, report, verify_declaration
from ml.v2_features import FEATURES, build_features
from ml.v2_shadow import create_replay_pair, readiness, read_record, reconcile_pair, write_record


def fixture():
    values = [(2010, 1, "2010-09-12", "A", "B", 21, 7, 7., 4.),
              (2011, 1, "2011-09-11", "A", "B", 14, 21, 6., 5.),
              (2011, 2, "2011-09-15", "B", "C", 10, 20, 4., 7.),
              (2011, 3, "2011-09-25", "A", "C", 20, 20, 5., 6.),
              (2011, 4, "2011-10-02", "A", "B", 35, 7, 8., 3.)]
    games, totals = [], []
    for s, w, day, h, a, hs, aws, hy, ay in values:
        gid = f"{s}_{w}_{a}_{h}"
        games.append(dict(game_id=gid, season=s, week=w, gameday=day, gametime="13:00", game_type="REG",
                          home_team=h, away_team=a, home_score=hs, away_score=aws))
        for own, opp, y, allowed in ((h, a, hy, ay), (a, h, ay, hy)):
            totals.append(dict(game_id=gid, season=s, team=own, opponent=opp, valid=True, reason="",
                               yards=y*60, plays=60, allowed_yards=allowed*60, allowed_plays=60))
    return pd.DataFrame(games), pd.DataFrame(totals)


def test_declaration_and_incumbent_integrity():
    assert verify_declaration()["config"]["features"] == FEATURES
    assert len(FEATURES) == 7
    assert frozen_model()["id"] == "schedule-v1-741cf41752"


@pytest.mark.parametrize("season", [2009, 2024, 2025, 2026, True, "2023"])
def test_acquisition_allowlist_checked_before_fetch(season):
    with pytest.raises(ValueError, match="Protected"):
        check_year(season)


def test_scrimmage_definition_sacks_scrambles_and_exclusions():
    games, _ = fixture()
    game = games.iloc[[0]]
    plays = []
    for index, (kind, yards, kneel, spike, two) in enumerate([
        ("pass", -8, 0, 0, 0), ("run", 12, 0, 0, 0), ("pass", 0, 0, 1, 0),
        ("run", -1, 1, 0, 0), ("run", 2, 0, 0, 1), ("no_play", 50, 0, 0, 0), ("kickoff", 60, 0, 0, 0)]):
        for own, opp in [("A", "B"), ("B", "A")]:
            plays.append(dict(zip(COLUMNS, [2010, "REG", game.iloc[0].game_id, index*2+(own=="B"), own, opp,
                                           kind, yards, kneel, spike, two], strict=True)))
    data = pd.DataFrame(plays)
    result = aggregate(data, game, 2010)
    assert result.valid.all() and result.plays.tolist() == [2, 2]
    assert result.yards.tolist() == [4., 4.]
    data.loc[0, "yards_gained"] = np.nan
    assert not aggregate(data, game, 2010).valid.any()
    data.loc[0, "season"] = 2025
    with pytest.raises(ValueError, match="mixed/protected"):
        aggregate(data, game, 2010)


def test_exact_incumbent_parity_reset_week_one_and_prior_margin():
    games, totals = fixture()
    rows = build_features(games, totals)
    np.testing.assert_array_equal(rows[V1_FEATURES], v1_features(games)[V1_FEATURES])
    first = rows.iloc[1]
    assert first.eligible
    assert first[V1_FEATURES].tolist() == [0., 0., 0., 0.]
    assert first.prior_margin_diff == pytest.approx(28/5)
    assert first.adjusted_offense_ypp_diff == first.adjusted_defense_ypp_diff == 0
    assert not rows.iloc[2].eligible  # C has no previous-year record


def test_adjustment_matches_hand_calculation_with_only_pregame_opponent():
    games, totals = fixture()
    final = build_features(games, totals).iloc[-1]
    # A: game1 6-5.5 against neutral B; game3 5-5.5 minus C defense (4-5.5)/5.
    # B: game1 5-5.5 against neutral A; game2 4-5.5 against neutral C.
    expected_off = (.5 + (-.5 - (-1.5/5)))/6 - (-.5 - 1.5)/6
    # A defense: -.5; then +.5 minus C offense +1.5/5.
    # B defense: +.5; then +1.5 against neutral C.
    expected_def = (-.5 + (.5 - 1.5/5))/6 - (.5 + 1.5)/6
    assert final.adjusted_offense_ypp_diff == pytest.approx(expected_off)
    assert final.adjusted_defense_ypp_diff == pytest.approx(expected_def)
    for entry in final.efficiency_history:
        assert entry["gameday"] < final.gameday
        assert all(day < entry["gameday"] for day in entry["opponent_history_dates"])


def test_current_future_results_and_pbp_cannot_enter_own_features():
    games, totals = fixture()
    original = build_features(games, totals)
    games.loc[3:, ["home_score", "away_score"]] = [99, 0]
    totals.loc[totals.game_id.isin(games.iloc[3:].game_id), ["yards", "allowed_yards"]] = 900
    changed = build_features(games, totals)
    np.testing.assert_array_equal(original.iloc[:4][FEATURES], changed.iloc[:4][FEATURES])


def test_later_opponent_games_cannot_rewrite_earlier_adjustment():
    games, totals = fixture()
    original = build_features(games, totals).iloc[-1]
    # Alter C's later matchup against A; B's adjustment against C must stay fixed.
    selected = totals.game_id.eq(games.iloc[3].game_id)
    totals.loc[selected, ["yards", "allowed_yards"]] = 1200
    modified = build_features(games, totals).iloc[-1]
    before = [h for h in original.efficiency_history if h["team"] == "B"]
    after = [h for h in modified.efficiency_history if h["team"] == "B"]
    assert before == after


def test_order_same_day_byes_and_unusual_week_numbers():
    games, totals = fixture()
    expected = build_features(games, totals)
    pd.testing.assert_frame_equal(expected, build_features(games.sample(frac=1, random_state=42), totals.sample(frac=1, random_state=3)))
    # On Sep25 A rested14 days and C10, independent of nominal week labels.
    assert expected.iloc[3].rest_diff == 4
    games.loc[2, "gameday"] = games.loc[3, "gameday"]
    games.loc[2, "week"] = 8
    row = build_features(games, totals).set_index("game_id").loc[games.iloc[3].game_id]
    assert row.away_games == 0
    assert all(d < row.gameday for d in row.history_dates)


@pytest.mark.parametrize("before,after", [("STL", "LA"), ("SD", "LAC"), ("OAK", "LV"), ("AZ", "ARI"), ("LAR", "LA")])
def test_franchise_identity_changes(before, after):
    games, totals = fixture()
    games = games.replace({"A": before})
    totals = totals.replace({"A": before})
    for data in (games, totals):
        fields = ["home_team", "away_team"] if "home_team" in data else ["team", "opponent"]
        data.loc[data.season.eq(2011), fields] = data.loc[data.season.eq(2011), fields].replace({before: after})
    first = build_features(games, totals).iloc[1]
    assert first.eligible and first.prior_margin_diff == pytest.approx(28/5)


def test_missing_pbp_propagates_without_changing_target_features():
    games, totals = fixture()
    totals = totals[~totals.game_id.eq(games.iloc[1].game_id)]
    rows = build_features(games, totals)
    assert rows.iloc[1].eligible  # target play-by-play is never an input
    assert not rows.iloc[2].eligible
    assert "missing preceding current-season efficiency" in rows.iloc[2].unavailable_reasons
    assert "missing opponent pregame efficiency" in rows.iloc[3].unavailable_reasons


def test_missing_scores_prior_and_nonfinite_data_fail_closed():
    games, totals = fixture()
    games.loc[0, "home_score"] = np.nan
    assert not build_features(games, totals).iloc[1].eligible
    games, totals = fixture()
    games.loc[1, "home_score"] = np.nan
    assert "missing preceding current-season result" in build_features(games, totals).iloc[3].unavailable_reasons
    totals.loc[0, "yards"] = float("inf")
    with pytest.raises(ValueError, match="efficiency total"):
        build_features(games, totals)


def test_duplicate_totals_identity_disagreement_and_protected_features():
    games, totals = fixture()
    with pytest.raises(ValueError, match="Duplicate"):
        build_features(games, pd.concat([totals, totals.iloc[[0]]]))
    broken = totals.copy()
    broken.loc[0, "allowed_yards"] = 99
    with pytest.raises(ValueError, match="disagree"):
        build_features(games, broken)
    games.loc[0, "season"] = 2025
    with pytest.raises(ValueError, match="Protected"):
        build_features(games, totals)


def test_training_boundary_rejects_before_fitting():
    frame = pd.DataFrame({"season": [2025], "home_win": [1]})
    with pytest.raises(ValueError, match="chronological"):
        fit_fold(frame, frame, FEATURES)


def test_calibration_fixed_bins_zero_one_empty_and_known_ece():
    result = calibration([0, 1, 0, 1], [0, .9, .2, 1])
    assert len(result["bins"]) == 10
    assert result["bins"][9]["count"] == 2
    assert result["bins"][1]["predicted"] is None
    assert result["ece"] == pytest.approx(.075)


def test_paired_block_uncertainty_matches_independent_concatenation_oracle():
    rows = [{"season": season, "week": week, "game_id": f"{season}-{week}-{i}", "home_win": i % 2,
             "probabilities": {"v2": .2 + .15*i, "four_feature": .5}}
            for season, week, i in [(2022, 1, 0), (2022, 1, 1), (2022, 2, 2), (2023, 1, 0), (2023, 2, 1)]]
    actual = report(rows, ["v2", "four_feature"])
    rng = np.random.default_rng(42)
    values = []
    for _ in range(2000):
        sample = []
        for season in [2022, 2023]:
            blocks = [[r for r in rows if r["season"] == season and r["week"] == week] for week in [1, 2]]
            sample.extend(r for i in rng.integers(2, size=2) for r in blocks[i])
        values.append(np.mean([(r["probabilities"]["v2"]-r["home_win"])**2 - (.5-r["home_win"])**2 for r in sample]))
    expected = np.quantile(values, [.025, .975])
    assert actual["v2_minus_comparator"]["brier"]["low"] == pytest.approx(expected[0])
    assert actual["v2_minus_comparator"]["brier"]["high"] == pytest.approx(expected[1])
    assert actual == report(list(reversed(rows)), ["v2", "four_feature"])


def saved_result():
    receipts = sorted(DIRECTORY.glob("receipt-*.json"))
    if not receipts:
        pytest.skip("V2 experiment not fitted yet")
    receipt = max((json.loads(p.read_bytes()) for p in receipts), key=lambda r: r["completed_at"])
    body = (DIRECTORY / receipt["result_file"]).read_bytes()
    assert sha(body) == receipt["sha256"]
    assert receipt["repeat_verified"]
    return json.loads(body), receipt


def test_saved_models_probabilities_metrics_and_train_only_scaler():
    result, receipt = saved_result()
    raw = (DIRECTORY / receipt["feature_file"]).read_bytes()
    assert sha(raw) == receipt["feature_sha256"]
    rows = pd.read_csv(DIRECTORY / receipt["feature_file"])
    for fold in result["folds"]:
        train = rows[rows.season.between(*fold["train_seasons"]) & rows.eligible & rows.complete & ~rows.is_tie]
        held = [r for r in result["predictions"] if r["season"] == fold["season"]]
        x = pd.DataFrame([r["features"] for r in held])
        for model_key, p_key in [("v2_model", "v2"), ("four_feature_model", "four_feature")]:
            model = fold[model_key]
            assert model["fit_seasons"][1] < model["calibration"]["season"] < fold["season"]
            np.testing.assert_allclose(model["preprocessing"]["mean"], train[model["features"]].mean(), atol=1e-12)
            np.testing.assert_allclose(model["preprocessing"]["scale"], train[model["features"]].std(ddof=0), atol=1e-12)
            # Independent scalar logit and Platt reconstruction.
            probabilities = []
            for r in held:
                z = model["intercept"] + sum(r["features"][f]*c for f, c in zip(model["features"], model["coefficients"], strict=True))
                z = model["calibration"]["intercept"] + model["calibration"]["coefficient"]*z
                probabilities.append(1/(1+np.exp(-z)))
            np.testing.assert_allclose(probabilities, [r["probabilities"][p_key] for r in held], atol=1e-14)
            y = np.array([r["home_win"] for r in held])
            p = np.array(probabilities)
            measured = fold["report"]["models"][p_key]
            assert measured["brier"] == pytest.approx(np.mean((p-y)**2), abs=1e-14)
            assert measured["accuracy"] == np.mean((p >= .5) == y)
            assert measured["log_loss"] == pytest.approx(np.mean(-y*np.log(p)-(1-y)*np.log1p(-p)), abs=1e-14)
    assert result["frozen_v1_2023"]["frozen_v1_full_2023"]["brier"] == pytest.approx(.23704473172141693, abs=1e-14)
    assert result["promotion_eligible"] is False and result["shadow_2026_enabled"] is False


@pytest.mark.skipif(not (ROOT / "data/schedules-2010-2023.csv").exists(), reason="Approved local raw schedule required; no CI downloads")
def test_all_features_reproduce_from_sealed_inputs():
    result, receipt = saved_result()
    games, _ = load_snapshot()
    totals, manifest = load_inputs()
    all_rows = build_features(games, totals).set_index("game_id")
    for row in result["predictions"]:
        assert all_rows.loc[row["game_id"], FEATURES].to_dict() == row["features"]
    assert set(totals.season) == set(range(2010, 2024))
    assert all(s["season"] < 2024 for s in manifest["sources"])
    for row in all_rows.itertuples():
        assert all(day < row.gameday for day in row.history_dates)
        assert all(day < h["gameday"] for h in row.efficiency_history for day in h["opponent_history_dates"])


def test_current_shadow_stays_disabled_even_if_inputs_claimed_available():
    for season in [2024, 2025, 2026]:
        assert "Protected" in readiness(season, inputs_available=True)["reason"]
        assert readiness(season)["enabled"] is False
    assert readiness(2027)["enabled"] is False


def test_paired_ledger_immutable_separate_and_reconciliation(tmp_path):
    result, _ = saved_result()
    sample = copy.deepcopy(next(r for r in result["predictions"] if r["season"] == 2023))
    parts = sample["game_id"].split("_")
    row = dict(sample, **sample["features"], eligible=True, history_dates=[], history_ids=[], home_team=parts[-1], away_team=parts[-2])
    kickoff = row["gameday"] + "T17:00:00+00:00"
    pair = create_replay_pair(row, result["model"], "a"*64, kickoff)
    assert pair["prospective"] is False
    assert pair["generated_at"] > pair["cutoff"]  # actual generation, not a fabricated pregame date
    first = write_record(pair, directory=tmp_path)
    assert first == write_record(pair, directory=tmp_path)
    assert read_record(first) == pair
    with pytest.raises(ValueError, match="checksum"):
        read_record(dict(first, sha256="c"*64))
    assert len(list(tmp_path.rglob("*.json"))) == 1
    final = {k: pair[k] for k in ("game_id", "season", "home_team", "away_team", "kickoff")}
    final.update(status="FINAL", verified=True, home_score=21, away_score=14,
                 observed_at="2026-10-24T12:00:00Z", source_sha256="b"*64)
    scored = reconcile_pair(pair, final)
    assert scored["scores"]["v2"]["brier"] == pytest.approx((pair["models"]["v2"]["probability"]-1)**2)
    assert scored["scores"]["v1"]["brier"] == pytest.approx((pair["models"]["v1"]["probability"]-1)**2)
    write_record(scored, "reconciliation", tmp_path)
    assert sha(Path(first["file"]).read_bytes()) == first["sha256"]
    final["away_score"] = 21
    assert reconcile_pair(pair, final)["excluded_reason"] == "tie"
    final["kickoff"] = "2023-09-11T17:00:00Z"
    with pytest.raises(ValueError, match="identity"):
        reconcile_pair(pair, final)
    with pytest.raises(ValueError, match="isolated"):
        write_record(pair, directory=ROOT / "web/public/data/current")
    with pytest.raises(ValueError, match="isolated"):
        write_record(pair, directory=ROOT / "docs")
