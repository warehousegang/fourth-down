"""Synthetic current-season edge cases; no holdout outcomes or fitting."""
import copy
import csv
import io
import json
from datetime import datetime, timezone

import pandas as pd
import pytest

from ml.current import feature_state, frozen_model, generate, observed_finals, publish_local
from ml.current_source import canonical, check_season, current_season, normalize, sha, timestamp
from ml.features import FEATURES, build_features


def game(id, week, day, home="DET", away="GB", hs=None, aws=None, phase="", kickoff=True):
    return {"id": f"ngs-2026-{id}", "source_game_id": id, "season": 2026, "week": week,
            "home": home, "away": away, "day": day, "kickoff": day+"T17:00:00+00:00" if day and kickoff else None,
            "home_score": hs, "away_score": aws, "phase": phase, "validated": phase.startswith("FINAL"),
            "stadium": "Test venue"}


def snapshot(games=None, observed="2026-09-12T12:00:00+00:00"):
    return {"schema_version": 1, "season": 2026, "retrieved_at": observed, "source_updated_at": observed,
            "source_url": "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/nfl_ngs_schedules/ngs_schedule_2026.csv",
            "raw_sha256": "a"*64, "asset_id": 1, "source_name": "Synthetic test", "license_url": "https://example.com/license",
            "games": games or [game("one", 1, "2026-09-06", hs=21, aws=14, phase="FINAL"),
                              game("two", 2, "2026-09-13"), game("future", 3, "2026-09-20")]}


def run(s, prior=(), as_of="2026-09-12T13:00:00+00:00"):
    return generate(s, list(prior), as_of, as_of)


def test_future_and_target_results_cannot_enter_state():
    base = snapshot()
    before = run(base)["games"][0]
    altered = copy.deepcopy(base)
    for g in altered["games"][1:]:
        g.update(home_score=99, away_score=0)
    after = run(altered)["games"][0]
    assert after["home_probability"] == before["home_probability"]
    assert after["factors"] == before["factors"]
    assert len(after["history"]["home"]) == 1


def test_same_day_results_excluded_even_if_final():
    s = snapshot([game("a", 1, "2026-09-13", hs=50, aws=0, phase="FINAL"), game("b", 2, "2026-09-13")],
                 "2026-09-13T21:00:00+00:00")
    evidence = observed_finals([s], 2026)
    row, history = feature_state(s["games"][1], s["games"], evidence, timestamp("2026-09-13T22:00:00Z"))
    assert all(row[key] == 0 for key in FEATURES)
    assert history == {"home": [], "away": []}


def test_week_one_priors_and_no_prior_season_strength():
    s = snapshot([game("opener", 1, "2026-09-13")])
    g = run(s)["games"][0]
    assert g["status"] == "available"
    assert all(f["difference"] == 0 for f in g["factors"])
    assert g["factors"][0]["home"] == .5
    assert g["factors"][3]["home"] == 7
    assert g["warnings"]
    mixed = copy.deepcopy(s)
    mixed["games"][0]["season"] = 2023
    with pytest.raises(ValueError, match="Mixed/protected"):
        run(mixed)


@pytest.mark.parametrize("season", [2024, 2025, 2023])
def test_protected_seasons_rejected_before_acquisition(season, monkeypatch):
    from ml import current_source
    monkeypatch.setattr(current_source, "download", lambda *a: pytest.fail("Network must not be called"))
    with pytest.raises(ValueError, match="Protected"):
        current_source.acquire(season)


def test_bye_rest_cap_and_completed_tie():
    s = snapshot([game("tie", 1, "2026-08-30", hs=10, aws=10, phase="FINAL"), game("next", 3, "2026-09-13")])
    g = run(s)["games"][0]
    assert g["factors"][0]["home"] == .5  # (half win + 2) / (1 + 4)
    assert g["factors"][3]["home"] == 14


@pytest.mark.parametrize("change,reason", [
    ({"home_score": None}, "not confirmed"),
    ({"phase": "IN_PROGRESS"}, "not confirmed"),
    ({"validated": False}, "not confirmed"),
    ({"day": None, "kickoff": None}, "Unknown date"),
])
def test_incomplete_history_fails_closed(change, reason):
    s = snapshot()
    s["games"][0].update(change)
    g = run(s)["games"][0]
    assert g["status"] == "unavailable" and reason in g["reason"]
    assert g["home_probability"] is None and not g["factors"]


def test_late_observation_cannot_be_backdated_but_prior_snapshot_proves_availability():
    prior = snapshot()
    late = snapshot(observed="2026-09-13T12:00:00+00:00")
    blocked = run(late, as_of="2026-09-13T13:00:00Z")["games"][0]
    assert blocked["status"] == "unavailable"
    good = run(late, [prior], "2026-09-13T13:00:00Z")["games"][0]
    assert good["status"] == "available"
    late["games"][0]["home_score"] = 24  # A corrected score cannot inherit old observation evidence.
    assert run(late, [prior], "2026-09-13T13:00:00Z")["games"][0]["status"] == "unavailable"


@pytest.mark.parametrize("change,reason", [
    ({"kickoff": None}, "unconfirmed"),
    ({"kickoff": None, "day": None}, "unconfirmed"),
    ({"phase": "POSTPONED"}, "POSTPONED"),
    ({"phase": "SUSPENDED"}, "SUSPENDED"),
])
def test_unconfirmed_or_postponed_games_have_no_probability(change, reason):
    s = snapshot()
    s["games"][1].update(change)
    # Keep another confirmed Week 2 game to establish current week when time is absent.
    s["games"].append(game("other", 2, "2026-09-13", "KC", "BUF"))
    g = next(g for g in run(s)["games"] if g["id"] == "ngs-2026-two")
    assert g["status"] == "unavailable" and reason in g["reason"]
    assert g["home_probability"] is None


def test_reschedule_retains_identity_changes_rest_version_and_warning(tmp_path):
    old = snapshot()
    moved = copy.deepcopy(old)
    moved["games"][1].update(day="2026-09-14", kickoff="2026-09-14T17:00:00+00:00")
    old_artifact, new_artifact = run(old), run(moved, [old])
    a, b = old_artifact["games"][0], new_artifact["games"][0]
    assert a["id"] == b["id"] and a["schedule_fingerprint"] != b["schedule_fingerprint"]
    assert a["factors"][3]["home"] == 7 and b["factors"][3]["home"] == 8
    assert "Schedule changed" in b["warnings"][0]
    assert publish_local(old_artifact, tmp_path) != publish_local(new_artifact, tmp_path)
    assert len(list(tmp_path.glob("forecast-*.json"))) == 2


def test_reproducibility_and_canonical_pointer(tmp_path):
    one, two = run(snapshot()), run(snapshot())
    assert canonical(one) == canonical(two)
    path = publish_local(one, tmp_path)
    assert path == publish_local(two, tmp_path)
    pointer = json.loads((tmp_path / "latest.json").read_text())
    assert pointer["sha256"] == sha(path.read_bytes())
    assert path.name == pointer["file"]
    model = frozen_model()
    assert one["model"] == model
    assert one["games"][0]["away_probability"] == 1-one["games"][0]["home_probability"]


def test_stale_snapshot_and_invalid_time_fail_closed():
    s = snapshot()
    s["source_updated_at"] = "2026-09-09T00:00:00Z"
    assert run(s)["games"][0]["status"] == "unavailable"
    with pytest.raises(ValueError, match="time ordering"):
        run(s, as_of="2026-09-11T00:00:00Z")
    assert current_season(timestamp("2027-01-03T12:00:00Z")) == 2026


def test_feature_adapter_matches_unchanged_historical_builder():
    s = snapshot([game("a", 1, "2026-09-01", hs=14, aws=7, phase="FINAL"),
                  game("b", 2, "2026-09-08", hs=10, aws=10, phase="FINAL"), game("c", 3, "2026-09-20")],
                 "2026-09-19T12:00:00Z")
    current, _ = feature_state(s["games"][2], s["games"], observed_finals([s], 2026), timestamp("2026-09-19T12:00:01Z"))
    # Synthetic pre-2024 counterpart, never relabel any real/protected data.
    historical = pd.DataFrame([{ "game_id": g["id"], "season": 2023, "week":g["week"], "game_type":"REG",
        "gameday": g["day"].replace("2026", "2023"), "gametime":"13:00", "home_team":g["home"], "away_team":g["away"],
        "home_score":g["home_score"], "away_score":g["away_score"]} for g in s["games"]])
    expected = build_features(historical).iloc[-1]
    for key in FEATURES:
        assert current[key] == expected[key]
        for side in ("home", "away"):
            name = f"{side}_{key.removesuffix('_diff')}"
            assert current[name] == expected[name]


def test_source_mixed_seasons_and_partial_coverage_rejected():
    with pytest.raises(ValueError, match="Mixed"):
        normalize(b"season,home_score\n2025,DO_NOT_PARSE\n", 2026)
    with pytest.raises(ValueError, match="Missing source"):
        normalize(b"season\n2026\n", 2026)


def test_observation_exactly_at_cutoff_is_not_before_cutoff():
    g = run(snapshot(), as_of="2026-09-12T12:00:00Z")["games"][0]
    assert g["status"] == "unavailable"


def test_unknown_kickoff_does_not_skip_to_later_week():
    s = snapshot()
    s["games"][1].update(kickoff=None, day=None)
    a = run(s)
    assert a["week"] == 2
    assert [g["id"] for g in a["games"]] == ["ngs-2026-two"]
    assert a["games"][0]["home_probability"] is None


def test_postponed_game_retained_when_no_other_upcoming_games():
    s = snapshot([game("pending", 1, "2026-09-06", phase="POSTPONED")])
    a = run(s)
    assert a["games"][0]["status"] == "unavailable"
    assert "POSTPONED" in a["games"][0]["reason"]


def csv_bytes(rows):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode()


def source_rows():
    from datetime import timedelta
    from ml.current_source import TEAMS
    teams = sorted(TEAMS)
    rows = []
    for week in range(1, 18):
        day = (datetime(2026, 9, 1) + timedelta(days=(week-1)*7)).date()
        for index in range(16):
            rows.append(dict(season="2026", season_type="REG", week=str(week), game_key=str(len(rows)+1),
                game_id=str(len(rows)+1), game_time=f"{day}T17:00:00Z", game_date=day.strftime("%m/%d/%Y"),
                phase="", home_team_abbr=teams[index], visitor_team_abbr=teams[-index-1],
                home_score="", visitor_score="", validated="false"))
        teams = [teams[0], teams[-1], *teams[1:-1]]
    return rows


def test_source_coverage_aliases_duplicates_and_invalid_scores():
    rows = source_rows()
    for r in rows:
        r["home_team_abbr"] = {"ARI":"AZ", "LA":"LAR"}.get(r["home_team_abbr"], r["home_team_abbr"])
    normalized = normalize(csv_bytes(rows), 2026)
    assert len(normalized) == 272 and {"ARI", "LA"} <= {r["home"] for r in normalized}
    with pytest.raises(ValueError, match="Incomplete"):
        normalize(csv_bytes(rows[:-1]), 2026)
    duplicate = copy.deepcopy(rows)
    duplicate[-1]["game_key"] = duplicate[0]["game_key"]
    with pytest.raises(ValueError, match="Duplicate stable"):
        normalize(csv_bytes(duplicate), 2026)
    wrong_score = copy.deepcopy(rows)
    wrong_score[0]["home_score"] = "NaN"
    with pytest.raises(ValueError, match="Invalid score"):
        normalize(csv_bytes(wrong_score), 2026)
    duplicate_week = copy.deepcopy(rows)
    duplicate_week[-1]["week"] = "1"
    with pytest.raises(ValueError, match="Duplicate team/week"):
        normalize(csv_bytes(duplicate_week), 2026)


def test_failed_refresh_preserves_last_good_pointer(tmp_path, monkeypatch):
    from ml import current
    from ml import current_source
    import sys
    artifact = run(snapshot())
    destination = tmp_path / "web/public/data/current"
    publish_local(artifact, destination)
    before = (destination / "latest.json").read_bytes()
    raw = csv_bytes(source_rows())
    metadata = {"assets": [{"name":"ngs_schedule_2026.csv", "browser_download_url":current_source.DOWNLOAD+"/ngs_schedule_2026.csv", "digest":"sha256:"+"0"*64}]}
    monkeypatch.setattr(current_source, "ROOT", tmp_path)
    monkeypatch.setattr(current, "ROOT", tmp_path)
    monkeypatch.setattr(current_source, "current_season", lambda now: 2026)
    monkeypatch.setattr(current, "current_season", lambda now: 2026)
    monkeypatch.setattr(current_source, "download", lambda url: canonical(metadata) if url == current_source.RELEASE else raw)
    monkeypatch.setattr(sys, "argv", ["ml.current"])
    with pytest.raises(ValueError, match="Source changed"):
        current.main()
    assert (destination / "latest.json").read_bytes() == before
    assert len(list(destination.glob("forecast-*.json"))) == 1
    assert not (tmp_path / "data/current").exists()
