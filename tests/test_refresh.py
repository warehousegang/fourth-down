"""Bounded operational scheduling and failure tests, synthetic seasons only."""
import copy
import io
import json
from urllib.error import HTTPError, URLError

import pytest

from ml.current import generate, publish_local
from ml.current_source import canonical, sha, timestamp
from ml.refresh import acquire_bounded, finalize_generation, plan_refresh, refresh, refresh_lock


def sample():
    return {"schema_version":1,"season":2026,"retrieved_at":"2026-10-20T12:00:00Z","source_updated_at":"2026-10-20T11:00:00Z",
            "source_url":"https://github.com/sportsdataverse/sportsdataverse-data/releases/download/nfl_ngs_schedules/ngs_schedule_2026.csv",
            "raw_sha256":"a"*64,"asset_id":1,"source_name":"Synthetic test","license_url":"https://example.com/license",
            "games":[{"id":"ngs-2026-1","source_game_id":"test","season":2026,"week":7,"home":"DET","away":"GB",
                      "day":"2026-10-25","kickoff":"2026-10-25T13:30:00Z","phase":"","home_score":None,"away_score":None,"validated":False,"stadium":"Synthetic"}]}


def test_planner_uses_international_kickoff_and_explicit_result_checks():
    plan=plan_refresh(sample(),"2026-10-20T12:01:00Z")
    assert not plan["enabled"]
    pre=next(e for e in plan["events"] if e["kind"]=="pregame")
    assert timestamp(pre["due_at"])==timestamp("2026-10-25T12:00:00Z")
    assert pre["latest_safe_start"]=="2026-10-25T13:30:00+00:00"
    assert {e["kind"] for e in plan["events"]}=={"early_week","saturday_evening","pregame","verify_result"}
    assert len([e for e in plan["events"] if e["kind"]=="verify_result"])==3


def test_missed_schedule_never_backdates_or_runs_after_kickoff():
    before=plan_refresh(sample(),"2026-10-25T13:00:00Z")
    assert len(before["missed_pregame_opportunities"])==1
    assert not [e for e in before["events"] if e["kind"]=="pregame"]
    after=plan_refresh(sample(),"2026-10-25T14:00:00Z")
    assert not after["missed_pregame_opportunities"]
    assert all(timestamp(e["due_at"])>timestamp(after["planned_at"]) for e in after["events"])


def test_unknown_and_postponed_times_do_not_get_fabricated_pregame_runs():
    s=sample();s["games"][0]["kickoff"]=None
    plan=plan_refresh(s,"2026-10-20T12:01:00Z")
    assert plan["unconfirmed_kickoff_ids"]==["ngs-2026-1"]
    assert not any(e["game_ids"] for e in plan["events"])
    s=sample();s["games"][0]["phase"]="POSTPONED"
    assert not [e for e in plan_refresh(s,"2026-10-20T12:01:00Z")["events"] if e["kind"]=="pregame"]


def test_simultaneous_kickoffs_coalesce_and_plan_is_reproducible():
    s=sample();other=copy.deepcopy(s["games"][0]);other.update(id="ngs-2026-2",home="BUF",away="KC")
    s["games"].append(other)
    a=plan_refresh(s,"2026-10-20T12:01:00Z")
    assert a==plan_refresh(s,"2026-10-20T12:01:00Z")
    assert len(next(e for e in a["events"] if e["kind"]=="pregame")["game_ids"])==2


@pytest.mark.parametrize("change", ["protected","mixed","future","horizon"])
def test_plan_rejects_invalid_inputs(change):
    s=sample();kwargs={}
    if change=="protected":s["season"]=2025
    if change=="mixed":s["games"][0]["season"]=2025
    if change=="future":s["retrieved_at"]="2026-10-21T00:00:00Z"
    if change=="horizon":kwargs["horizon_days"]=30
    with pytest.raises(ValueError):plan_refresh(s,"2026-10-20T12:01:00Z",**kwargs)


def test_retry_is_bounded_and_rate_limits_are_not_retried():
    calls=[];pauses=[]
    def unavailable(season):
        calls.append(season);raise URLError("source unavailable")
    with pytest.raises(URLError):acquire_bounded(2026,unavailable,pauses.append)
    assert calls==[2026,2026] and pauses==[1]
    calls.clear();pauses.clear()
    def limited(season):
        calls.append(season);raise HTTPError("https://example.com",429,"rate limited",{},io.BytesIO())
    with pytest.raises(HTTPError):acquire_bounded(2026,limited,pauses.append)
    assert calls==[2026] and not pauses


def test_bad_schema_is_not_retried():
    def malformed(season):raise ValueError("bad source schema")
    with pytest.raises(ValueError):acquire_bounded(2026,malformed,lambda _:pytest.fail("No retry for invalid source"))


def test_concurrent_refresh_fails_without_stale_lock(tmp_path):
    with refresh_lock(tmp_path):
        with pytest.raises(RuntimeError,match="Another"):
            with refresh_lock(tmp_path):pass
    with refresh_lock(tmp_path):pass


def test_validation_failure_leaves_both_latest_pointers_untouched(tmp_path,monkeypatch):
    from ml import refresh as module
    current=tmp_path/"current";ops=tmp_path/"operations";current.mkdir();ops.mkdir()
    for p in (current,ops):(p/"latest.json").write_text("sentinel")
    s=sample();now=timestamp("2026-10-20T12:01:00Z")
    monkeypatch.setattr(module,"load_snapshot",lambda *args:s)
    monkeypatch.setattr(module,"snapshots_before",lambda *args:[s])
    monkeypatch.setattr(module,"load_forecasts",lambda *args:[])
    def failed(*args):raise ValueError("broken lifecycle proof")
    monkeypatch.setattr(module,"build_operations",failed)
    with pytest.raises(ValueError,match="broken lifecycle"):
        refresh(tmp_path/"snapshot.json",now=now,current_directory=current,operations_directory=ops)
    assert all((p/"latest.json").read_text()=="sentinel" for p in (current,ops))
    assert len(list(current.iterdir()))==1


def test_actual_time_refresh_preserves_versions_and_reproduces(tmp_path,monkeypatch):
    from ml import refresh as module
    s=sample();now=timestamp("2026-10-20T12:01:00Z")
    monkeypatch.setattr(module,"load_snapshot",lambda *args:s)
    monkeypatch.setattr(module,"snapshots_before",lambda *args:[s])
    current=tmp_path/"current";ops=tmp_path/"operations"
    a=refresh(tmp_path/"snapshot.json",now=now,current_directory=current,operations_directory=ops)
    b=refresh(tmp_path/"snapshot.json",now=now,current_directory=current,operations_directory=ops)
    assert a==b and a["available_forecasts"]==1 and not a["publicly_published"]
    original=(current/"latest.json").read_bytes()
    c=refresh(tmp_path/"snapshot.json",now=timestamp("2026-10-20T12:02:00Z"),current_directory=current,operations_directory=ops)
    assert c["current_artifact"]!=a["current_artifact"]
    assert len(list(current.glob("forecast-*.json")))==2
    assert (current/json.loads(original)["file"]).is_file()


def test_generation_crossing_kickoff_never_issues_pregame_probability():
    s=sample()
    s["source_updated_at"]="2026-10-25T10:00:00Z"
    s["retrieved_at"]="2026-10-25T10:01:00Z"
    # Week 1-style empty records keep this boundary independent of missing history.
    artifact=generate(s,[],"2026-10-25T13:29:59Z","2026-10-25T13:30:01Z")
    game=artifact["games"][0]
    assert game["home_probability"] is None and game["status"]=="unavailable"
    assert "Kickoff passed" in game["reason"]
    artifact=generate(s,[],"2026-10-25T13:29:59Z","2026-10-25T13:29:59Z")
    assert artifact["games"][0]["status"]=="available"
    finalize_generation(artifact,timestamp("2026-10-25T13:30:01Z"))
    assert artifact["games"][0]["status"]=="unavailable"
    assert not artifact["games"][0]["features"] and artifact["games"][0]["home_probability"] is None


def test_oversize_output_leaves_last_good_pointers(tmp_path,monkeypatch):
    from ml import refresh as module
    s=sample();now=timestamp("2026-10-20T12:01:00Z")
    monkeypatch.setattr(module,"load_snapshot",lambda *args:s)
    monkeypatch.setattr(module,"snapshots_before",lambda *args:[s])
    monkeypatch.setattr(module,"load_forecasts",lambda *args:[])
    monkeypatch.setattr(module,"MAX_UI_ARTIFACT_BYTES",10)
    current=tmp_path/"current";ops=tmp_path/"operations";current.mkdir();ops.mkdir()
    for p in (current,ops):(p/"latest.json").write_text("sentinel")
    with pytest.raises(ValueError,match="client budget"):
        refresh(tmp_path/"snapshot.json",now=now,current_directory=current,operations_directory=ops)
    assert all((p/"latest.json").read_text()=="sentinel" and len(list(p.iterdir()))==1 for p in (current,ops))
