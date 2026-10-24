"""Adversarial temporal tests and independent oracle checks."""
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ml.data import ROOT
from ml.features import FEATURES, build_features
from ml.forecast import score
from ml.train import fit_model, predict


def fixture():
    return pd.DataFrame([
        dict(game_id="one", season=2022, week=1, game_type="REG", gameday="2022-09-01", gametime="13:00", home_team="A", away_team="B", home_score=20, away_score=10),
        dict(game_id="same-day", season=2022, week=1, game_type="REG", gameday="2022-09-01", gametime="20:00", home_team="A", away_team="C", home_score=3, away_score=3),
        dict(game_id="two", season=2022, week=2, game_type="REG", gameday="2022-09-08", gametime="13:00", home_team="B", away_team="A", home_score=35, away_score=7),
        dict(game_id="three", season=2022, week=3, game_type="REG", gameday="2022-09-25", gametime="13:00", home_team="A", away_team="C", home_score=10, away_score=24),
        dict(game_id="reset", season=2023, week=1, game_type="REG", gameday="2023-09-07", gametime="13:00", home_team="A", away_team="B", home_score=20, away_score=10),
    ])


def test_current_future_and_same_day_results_cannot_change_features():
    data = fixture()
    before = build_features(data).set_index("game_id")
    altered = data.copy()
    altered.loc[altered.gameday.ge("2022-09-08"), ["home_score", "away_score"]] = [90, 0]
    after = build_features(altered).set_index("game_id")
    pd.testing.assert_frame_equal(before.loc[["one", "same-day", "two"], FEATURES], after.loc[["one", "same-day", "two"], FEATURES])
    assert before.loc["same-day", "home_games"] == 0
    assert before.loc["reset", FEATURES].eq(0).all()


def test_ties_affect_history_and_rest_cap_is_applied():
    data = build_features(fixture()).set_index("game_id")
    assert bool(data.loc["same-day", "is_tie"])
    assert data.loc["two", "away_smooth_win"] == pytest.approx((1.5 + 2) / (2 + 4))
    assert data.loc["two", "away_margin"] == pytest.approx(10 / 6)
    assert data.loc["three", "home_rest"] == 14
    assert data.loc["reset", "home_rest"] == 7


def test_missing_result_does_not_update_history_but_can_be_scored():
    data = fixture()
    data.loc[data.game_id.eq("one"), "away_score"] = np.nan
    features = build_features(data).set_index("game_id")
    assert not features.loc["one", "complete"]
    assert features.loc["two", "away_games"] == 1  # Only the completed tie.
    model = {"features": FEATURES, "coefficients": [.1, .1, .1, .1], "intercept": 0}
    assert score(model, features.loc["one"])[0] == .5


def test_permutation_invariance():
    pd.testing.assert_frame_equal(build_features(fixture()), build_features(fixture().sample(frac=1, random_state=9)))


@pytest.mark.parametrize("mutation,match", [
    (lambda x: x.assign(season=2024), "Protected"),
    (lambda x: x.assign(game_id="duplicate"), "duplicate"),
    (lambda x: x.assign(gameday=None), "Missing"),
    (lambda x: x.assign(home_score=-1), "Invalid score"),
    (lambda x: x.assign(home_team=x.away_team), "itself"),
    (lambda x: x.assign(season=2022.5), "integers"),
    (lambda x: x.assign(week=0), "integers"),
    (lambda x: x.drop(columns="away_score"), "Missing source"),
])
def test_invalid_inputs_fail_closed(mutation, match):
    with pytest.raises(ValueError, match=match):
        build_features(mutation(fixture()))


def test_independent_brute_force_oracle():
    """Recompute each team's history with a slow filter, without the production state machine."""
    raw = fixture()
    features = build_features(raw)
    for row in features.itertuples():
        for side in ["home", "away"]:
            team = getattr(row, f"{side}_team")
            prior = raw[(raw.season == row.season) & (raw.gameday < row.gameday) &
                        (raw.home_team.eq(team) | raw.away_team.eq(team))]
            margins = [g.home_score - g.away_score if g.home_team == team else g.away_score - g.home_score
                       for g in prior.itertuples()]
            wins = sum(1 if m > 0 else .5 if m == 0 else 0 for m in margins)
            assert getattr(row, f"{side}_smooth_win") == pytest.approx((wins + 2) / (len(prior) + 4))
            assert getattr(row, f"{side}_margin") == pytest.approx(sum(margins) / (len(prior) + 4))
            assert getattr(row, f"{side}_recent_margin") == pytest.approx(sum(margins[-5:]) / (min(5, len(prior)) + 2))


def test_missing_feature_is_never_turned_into_probability():
    row = build_features(fixture()).iloc[0].copy()
    row["margin_diff"] = np.nan
    with pytest.raises(ValueError, match="missing"):
        score({"features": ["margin_diff"], "coefficients": [1], "intercept": 0}, row)


def test_recent_window_expires_old_games():
    base = fixture().iloc[0].to_dict()
    rows = [{**base, "game_id": f"g{i}", "week": i + 1,
             "gameday": (pd.Timestamp("2022-09-01") + pd.Timedelta(days=7*i)).strftime("%Y-%m-%d"),
             "home_score": 10 + i, "away_score": 10} for i in range(8)]
    data = build_features(pd.DataFrame(rows))
    assert data.iloc[-1].home_recent_margin == pytest.approx(sum([2, 3, 4, 5, 6]) / 7)


@pytest.mark.skipif(not (ROOT / "data/manifest.json").exists(), reason="Local source snapshot not present")
def test_real_data_features_against_independent_history_queries():
    from ml.data import load_snapshot
    raw, _ = load_snapshot()
    actual = build_features(raw)
    for row in actual[actual.season.eq(2023)].itertuples():
        for side in ["home", "away"]:
            code = getattr(row, f"{side}_team")
            past = raw[(raw.season == 2023) & (raw.gameday < row.gameday)
                       & (raw.home_team.eq(code) | raw.away_team.eq(code))
                       & raw.home_score.notna() & raw.away_score.notna()].sort_values(["gameday", "game_id"])
            margins = np.where(past.home_team == code, past.home_score - past.away_score, past.away_score - past.home_score)
            wins = np.sum(margins > 0) + .5 * np.sum(margins == 0)
            assert getattr(row, f"{side}_smooth_win") == pytest.approx((wins + 2) / (len(past) + 4))
            assert getattr(row, f"{side}_margin") == pytest.approx(sum(margins) / (len(past) + 4))
            assert getattr(row, f"{side}_recent_margin") == pytest.approx(sum(margins[-5:]) / (min(5, len(past)) + 2))
            rest = min(14, (pd.Timestamp(row.gameday) - pd.Timestamp(past.iloc[-1].gameday)).days) if len(past) else 7
            assert getattr(row, f"{side}_rest") == rest


def test_preserved_originals_match_manifest():
    manifest = json.loads((ROOT / "legacy/SHA256.json").read_text())
    for filename, expected in manifest.items():
        assert hashlib.sha256((ROOT / "legacy" / filename).read_bytes()).hexdigest() == expected


def test_exported_probabilities_are_model_derived():
    artifact = json.loads((ROOT / "web/public/data/demo.json").read_text())
    model = artifact["model"]
    assert artifact["mode"] == "historical-replay"
    assert artifact["evaluation"]["holdout_status"] == "locked"
    assert {g["season"] for g in artifact["games"]} == {2023}
    assert len({g["id"] for g in artifact["games"]}) == len(artifact["games"])
    for game in artifact["games"]:
        assert game["model_id"] == model["id"]
        z = model["intercept"]
        for f, c, name in zip(game["factors"], model["coefficients"], model["features"], strict=True):
            assert f["key"] == name
            assert f["difference"] == pytest.approx(f["home"] - f["away"])
            assert f["contribution"] == pytest.approx(c * f["difference"])
            z += f["contribution"]
        assert game["home_probability"] == pytest.approx(1 / (1 + math.exp(-z)), abs=1e-12)


@pytest.mark.skipif(not (ROOT / "data/manifest.json").exists(), reason="Local source snapshot intentionally excluded from Git/CI")
def test_training_is_repeatable_and_matches_exported_model():
    from ml.data import load_snapshot
    raw, manifest = load_snapshot()
    data = build_features(raw)
    training = data[(data.season <= 2022) & data.complete & ~data.is_tie]
    validation = data[(data.season == 2023) & data.complete & ~data.is_tie]
    artifact = json.loads((ROOT / "web/public/data/demo.json").read_text())
    one = fit_model(artifact["model"]["kind"], training)
    two = fit_model(artifact["model"]["kind"], training)
    assert one == two
    assert one["coefficients"] == artifact["model"]["coefficients"]
    assert one["intercept"] == artifact["model"]["intercept"]
    assert len(training) == 3347 and len(validation) == 272
    assert manifest["sha256"] == artifact["model"]["source_sha256"]
    lookup = {g["id"]: g["home_probability"] for g in artifact["games"]}
    np.testing.assert_allclose(predict(one, validation), [lookup[x] for x in validation.game_id], atol=1e-12)
