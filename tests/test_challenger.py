"""No-fit contracts for the independently authorized research challenger."""
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ml.challenger import (CONFIG, FEATURES, ROOT, build_features, canonical, ece, frozen_model,
                           interval, metrics, predict, verify_declaration)
from ml.data import load_snapshot
from ml.intelligence import eligible_evidence


def fixture():
    values = [(2010, 1, "2010-09-12", "AAA", "BBB", 24, 10, "Home"),
              (2010, 2, "2010-09-19", "BBB", "AAA", 21, 21, "Home"),
              (2011, 1, "2011-09-11", "AAA", "BBB", 10, 20, "Home"),
              (2011, 3, "2011-09-25", "BBB", "AAA", 7, 17, "Neutral"),
              (2011, 4, "2011-10-02", "AAA", "BBB", 35, 31, "Home")]
    return pd.DataFrame([dict(game_id=f"{s}_{w}_{away}_{home}", season=s, week=w, gameday=day,
                              home_team=home, away_team=away, home_score=hs, away_score=aws,
                              game_type="REG", gametime="13:00", location=location)
                         for s,w,day,home,away,hs,aws,location in values])


def research():
    directory = ROOT / "web/public/data/research"
    pointer = json.loads((directory / "latest.json").read_text())
    raw = (directory / pointer["file"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == pointer["sha256"]
    return json.loads(raw)


def test_declared_protocol_matches_fixed_configuration_and_freeze():
    assert verify_declaration()["config"] == CONFIG
    assert frozen_model()["id"] == "schedule-v1-741cf41752"
    assert CONFIG["locked_seasons"] == [2024, 2025]


def test_target_future_and_same_date_results_do_not_enter_features():
    source = fixture()
    original = build_features(source).iloc[3]
    source.loc[3:, ["home_score", "away_score"]] = [99, 0]
    mutated = build_features(source).iloc[3]
    assert original[FEATURES].to_dict() == mutated[FEATURES].to_dict()
    assert all(day < original.gameday for day in original.history_dates)
    source.loc[2, "gameday"] = source.loc[3, "gameday"]
    same_day = build_features(source).set_index("game_id").loc[source.loc[3, "game_id"]]
    assert same_day.home_games == same_day.away_games == 0
    assert same_day.margin_diff == same_day.recent_margin_diff == 0


def test_week_one_prior_strength_tie_half_credit_and_bye():
    rows = build_features(fixture())
    first = rows.iloc[2]
    assert first.home_games == first.away_games == 0
    assert first.smooth_win_diff == first.margin_diff == first.rest_diff == 0
    assert first.prior_smooth_win_diff == pytest.approx(((1.5+2)/6)-((.5+2)/6))
    assert first.prior_margin_diff == pytest.approx(28/6)
    assert set(first.prior_history_ids) == set(fixture().iloc[:2].game_id)
    third = rows.iloc[3]
    assert third.rest_diff == third.bye_diff == 0  # both rested14days
    assert third.neutral_site == 1
    final = rows.iloc[4]
    # Neutral game did not enter either venue-role history.
    assert final.venue_margin_diff == pytest.approx(-10/5 - 10/5)


def test_prior_franchise_alias_uses_real_previous_season():
    source = fixture().replace({"AAA": "STL", "BBB": "SD"})
    source.loc[source.season.eq(2011), "home_team"] = source.loc[source.season.eq(2011), "home_team"].replace({"STL":"LA", "SD":"LAC"})
    source.loc[source.season.eq(2011), "away_team"] = source.loc[source.season.eq(2011), "away_team"].replace({"STL":"LA", "SD":"LAC"})
    rows = build_features(source)
    assert rows[rows.season.eq(2011)].eligible.all()
    assert rows.iloc[2].prior_margin_diff == pytest.approx(28/6)


def test_missing_prior_and_preceding_result_fail_closed():
    source = fixture()
    assert not build_features(source).iloc[0].eligible
    source.loc[2, "home_score"] = np.nan
    rows = build_features(source)
    assert not rows.iloc[3].eligible
    assert "preceding result missing" in rows.iloc[3].unavailable_reasons


@pytest.mark.parametrize("season", [2024, 2025, 2026])
def test_challenger_rejects_all_unsupported_seasons_without_fetch(season):
    source = fixture()
    source.loc[4, "season"] = season
    with pytest.raises(ValueError, match="Protected or unsupported"):
        build_features(source)


def test_opponent_adjustment_never_uses_opponents_later_strength():
    source = fixture()
    result = build_features(source).iloc[4].opponent_adjusted_margin_diff
    source.loc[4, ["home_score", "away_score"]] = [100, 0]
    assert build_features(source).iloc[4].opponent_adjusted_margin_diff == result
    # game1 margin is -10/+10, opponent's earlier season margin zero.
    # game2 margins +10/-10 with opponents' pregame margins +2/-2.
    assert result == pytest.approx(((-10+0)+(10+2))/6 - ((10+0)+(-10-2))/6)


def test_exported_predictions_models_metrics_and_temporal_splits_match():
    artifact = research()
    assert artifact["status"] == "research-only-not-promoted"
    assert artifact["promotion"]["eligible"] is False
    assert artifact["reproducibility"]["repeat_verified"] is True
    models = {fold["season"]: fold["model"] for fold in artifact["fold_models"]}
    for season, model in models.items():
        assert model["fit_seasons"][1] < model["calibration"]["season"] < season
        rows = [row for row in artifact["predictions"] if row["season"] == season]
        frame = pd.DataFrame([row["features"] for row in rows])
        p = predict(model, frame)
        np.testing.assert_allclose(p, [row["probabilities"]["challenger"] for row in rows], atol=1e-14)
        expected = metrics([row["home_win"] for row in rows], p)
        recorded = next(fold for fold in artifact["evaluation"]["backtests"] if fold["season"] == season)
        assert expected == recorded["metrics"]["challenger"]
        assert ("frozen_incumbent" in rows[0]["probabilities"]) == (season == 2023)
    raw = copy.deepcopy(artifact)
    verification = raw.pop("reproducibility")
    raw.pop("generated_at")
    assert hashlib.sha256(canonical(raw)).hexdigest() == verification["deterministic_payload_sha256"]
    assert artifact["evaluation"]["diagnostic_status"] == "selection-exposed-retrospective"
    assert len(artifact["domains"]) == 12
    assert all(domain["contribution"] is None for domain in artifact["domains"] if not domain["challenger_used"])


@pytest.mark.skipif(
    not (ROOT / "data/schedules-2010-2023.csv").is_file() or not (ROOT / "data/manifest.json").is_file(),
    reason="Requires the separately preserved, approved local 2010–2023 raw snapshot and manifest; never downloads historical data in CI",
)
def test_saved_feature_snapshot_reproduces_from_local_source():
    artifact = research()
    source, _ = load_snapshot()
    rows = build_features(source).set_index("game_id")
    for sample in artifact["predictions"]:
        assert rows.loc[sample["id"], FEATURES].to_dict() == sample["features"]
        assert sample["season"] not in (2024, 2025)


def test_bootstrap_uses_distinct_season_week_blocks_deterministically():
    args = ([0,1,0,1], [.3,.6,.2,.8], [.5]*4, [2022,2022,2023,2023], [1,2,1,2])
    first = interval(*args)
    assert first == interval(*args)
    assert first["unit"] == "season-week" and first["stratified_by_season"]
    assert first["low"] <= first["mean"] <= first["high"]
    assert ece([0,1], [.1,.9]) == pytest.approx(.1)


def evidence(domain="quarterback"):
    value = {"status":"starter_confirmed", "player_id":"synthetic-player"}
    if domain == "weather":
        value = {"kind":"forecast", "valid_for":"2026-10-25T17:00:00Z", "temperature_c":12}
    if domain == "injuries":
        value = {"availability":"out", "player_id":"synthetic-player"}
    if domain == "developments":
        value = {"category":"roster_transaction", "statement":"Synthetic test transaction"}
    return {"domain":domain, "game_id":"synthetic-2026", "team":"DET", "season":2026,
            "source_url":"https://www.nfl.com/synthetic-test", "source_sha256":"a"*64,
            "published_at":"2026-10-25T10:00:00Z", "observed_at":"2026-10-25T10:01:00Z",
            "retrieved_at":"2026-10-25T10:02:00Z", "valid_until":"2026-10-25T18:00:00Z",
            "verification":"verified", "license_reviewed":True, "phase":"pregame", "value":value}


def evaluate(records, hosts=("www.nfl.com",)):
    return eligible_evidence(records, game_id="synthetic-2026", team="DET", season=2026,
                             cutoff="2026-10-25T12:00:00Z", kickoff="2026-10-25T17:00:00Z", approved_hosts=hosts)


def test_verified_annotation_cannot_change_probability():
    result = evaluate([evidence()])
    assert result["status"] == "available"
    assert result["probability_adjustment"] is None and not result["model_feature_enabled"]
    assert not result["evidence"][0]["affects_probability"]
    assert evaluate([evidence()], hosts=())["status"] == "unavailable"


@pytest.mark.parametrize("field,value", [("published_at","2026-10-25T13:00:00Z"),
    ("retrieved_at","2026-10-25T13:00:00Z"), ("observed_at","2026-10-24T10:00:00Z"),
    ("valid_until","2026-10-25T11:00:00Z"), ("phase","postgame"), ("verification","conflicted"),
    ("license_reviewed",False), ("team","KC"), ("season",2025),
    ("source_url","https://attacker.example/nfl.com"), ("source_sha256","missing")])
def test_evidence_availability_failures(field,value):
    row = evidence()
    row[field] = value
    result = evaluate([row])
    assert result["status"] == "unavailable" and result["rejected"]


def test_unconfirmed_starters_observed_weather_unknown_injury_and_private_news_rejected():
    starter, weather, injury, news = evidence(), evidence("weather"), evidence("injuries"), evidence("developments")
    starter["value"]["status"] = "questionable"
    weather["value"]["kind"] = "observed"
    injury["value"]["availability"] = "unknown"
    news["value"]["category"] = "private_emotional_state"
    assert evaluate([starter,weather,injury,news])["status"] == "unavailable"
    assert len(evaluate([starter,weather,injury,news])["rejected"]) == 4


def test_conflicting_confirmed_starters_and_empty_feed_are_unavailable():
    first, second = evidence(), evidence()
    second["value"]["player_id"] = "different-player"
    result = evaluate([first, second])
    assert result["status"] == "unavailable"
    assert "Conflicting" in result["rejected"][0]["reason"]
    assert evaluate([])["status"] == "unavailable"


def test_registry_does_not_promote_or_change_frozen_artifacts():
    registry = json.loads((ROOT / "docs/MODEL_REGISTRY.json").read_text())
    assert registry["operational_model_id"] == frozen_model()["id"]
    assert registry["promotion_approval"] is None
    assert registry["models"][1]["operational_status"] == "ineligible"
    for model in registry["models"]:
        assert hashlib.sha256((ROOT / model["artifact"]).read_bytes()).hexdigest() == model["sha256"]


def test_stale_published_report_cannot_be_refreshed_by_rereading_it():
    row = evidence()
    row["published_at"] = "2026-10-20T10:00:00Z"
    result = evaluate([row])
    assert result["status"] == "unavailable"
    assert "Stale" in result["rejected"][0]["reason"]


def test_evidence_bounded_nonfinite_or_malformed_inputs_fail_closed():
    with pytest.raises(ValueError, match="bounded"):
        evaluate([evidence()] * 101)
    row = evidence("weather")
    row["value"]["temperature_c"] = float("nan")
    assert evaluate([row])["status"] == "unavailable"
    assert evaluate([None])["status"] == "unavailable"
    row = evidence()
    row["value"]["notes"] = "x" * 16384
    assert evaluate([row])["status"] == "unavailable"


def test_unknown_opponent_pregame_strength_propagates_missing_status():
    source = fixture()
    # CCC's incomplete game need not involve AAA/BBB to invalidate later opponent adjustment.
    extra = source.iloc[[2]].copy()
    extra["game_id"] = "2011_1_CCC_DDD"
    extra["home_team"], extra["away_team"] = "CCC", "DDD"
    extra["home_score"] = np.nan
    source.loc[3, ["home_team", "away_team"]] = ["AAA", "CCC"]
    rows = build_features(pd.concat([source, extra], ignore_index=True)).set_index("game_id")
    # AAA's next adjustment depends on CCC's missing pregame strength, even though AAA scores exist.
    assert not rows.loc[source.iloc[4].game_id, "eligible"]


def test_missing_venue_status_is_unavailable_and_not_silently_home():
    source = fixture()
    source.loc[2, "location"] = None
    rows = build_features(source)
    assert not rows.iloc[2].eligible
    assert not rows.iloc[3].eligible
    assert "venue-role metadata unavailable" in rows.iloc[3].unavailable_reasons
