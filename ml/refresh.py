"""Explicit local forecasting + reconciliation; planner never enables a scheduler."""
import argparse
import fcntl
import json
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError

from ml.data import ROOT
from ml.current import generate, publish_local
from ml.current_source import (EASTERN, FINAL, SCHEDULED, acquire, canonical, check_season,
                               current_season, iso, load_snapshot, sha, timestamp)
from ml.lifecycle import build_operations, load_forecasts, publish_operations
from ml.freshness import select_display_forecast

MAX_UI_ARTIFACT_BYTES = 5_000_000


def verify_publication_budget(current, operations):
    """Fail before either pointer changes when static clients cannot read an output."""
    for name, artifact in (("current", current), ("operations", operations)):
        limit = min(MAX_UI_ARTIFACT_BYTES, 1_000_000) if name == "current" else MAX_UI_ARTIFACT_BYTES
        if len(canonical(artifact)) > limit:
            raise ValueError(f"{name} artifact exceeds the client budget ({limit} bytes); partition history before publication")
    if len(operations["catalog"]) > 10_000:
        raise ValueError("Operations catalog exceeds client budget; partition history before publication")


@contextmanager
def refresh_lock(directory=None):
    """OS-released local lock; a crashed process cannot leave a stale held lock."""
    directory = Path(directory or ROOT / "data/current")
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".refresh.lock").open("a") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("Another local refresh is running; current pointers were not changed") from error
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def acquire_bounded(season, fetch=None, pause=None):
    """At most two attempts. Rate limits are surfaced, never aggressively retried."""
    check_season(season)
    fetch, pause = fetch or acquire, pause or time.sleep
    for attempt in range(2):
        try:
            return fetch(season)
        except HTTPError as error:
            if error.code == 429 or error.code < 500 or attempt:
                raise
        except (URLError, TimeoutError):
            if attempt:
                raise
        pause(1)
    raise RuntimeError("Acquisition attempts exhausted")


def snapshots_before(path, season, now):
    snapshots = []
    for candidate in sorted(Path(path).parent.glob("snapshot-*.json")):
        snapshot = load_snapshot(candidate, season)
        if timestamp(snapshot["retrieved_at"]) <= now:
            snapshots.append(snapshot)
    return sorted(snapshots, key=lambda s: (s["retrieved_at"], sha(canonical(s))))


def plan_refresh(snapshot, now=None, horizon_days=7):
    """Bounded advisory plan based on real kickoff times; no execution side effects."""
    season = snapshot["season"]
    check_season(season)
    now = timestamp(now) if isinstance(now, str) else now or datetime.now(timezone.utc)
    if now.tzinfo is None or not 1 <= horizon_days <= 7:
        raise ValueError("Timezone-aware time and horizon of 1–7 days required")
    if any(g["season"] != season for g in snapshot["games"]):
        raise ValueError("Mixed/protected season in plan")
    if timestamp(snapshot["retrieved_at"]) > now:
        raise ValueError("Plan cannot precede source observation")
    end = now + timedelta(days=horizon_days)
    events = []
    def add(due, kind, game_id=None, deadline=None):
        if now < due <= end:
            events.append({"due_at": iso(due), "kind": kind, "game_ids": [game_id] if game_id else [],
                           "latest_safe_start": iso(deadline) if deadline else None})
    local_day = now.astimezone(EASTERN).date()
    for offset in range(horizon_days+1):
        day = local_day + timedelta(days=offset)
        if day.weekday() in (1, 5):
            due = datetime.combine(day, datetime.min.time(), EASTERN).replace(hour=9 if day.weekday() == 1 else 18)
            add(due, "early_week" if day.weekday() == 1 else "saturday_evening")
    missing = []
    overdue = []
    for game in snapshot["games"]:
        if game["phase"] in FINAL | {"CANCELLED"}:
            continue
        if not game["kickoff"]:
            missing.append(game["id"])
            continue
        kick = timestamp(game["kickoff"])
        if game["phase"] in SCHEDULED and now < kick:
            due = kick-timedelta(minutes=90)
            if due <= now:
                overdue.append({"game_id":game["id"], "kind":"pregame", "deadline":iso(kick),
                                "action":"Run at actual current time only if kickoff remains in the future; never backdate."})
            else:
                add(due, "pregame", game["id"], kick)
        # These are opportunities to CHECK for final status, never inferred end times.
        for hours in (4, 8, 24):
            add(kick+timedelta(hours=hours), "verify_result", game["id"])
    grouped = []
    for event in sorted(events, key=lambda e:(e["due_at"],e["kind"])):
        group = next((g for g in reversed(grouped) if g["kind"] == event["kind"]
                      and timestamp(event["due_at"])-timestamp(g["due_at"]) <= timedelta(minutes=30)), None)
        if group:
            group["game_ids"] = sorted(set(group["game_ids"]+event["game_ids"]))
            if event["latest_safe_start"]:
                group["latest_safe_start"] = min(group["latest_safe_start"],event["latest_safe_start"])
        else:
            grouped.append(event)
    if len(grouped) > 32:
        raise ValueError("Plan exceeds 32-run review budget; no scheduler has been enabled")
    return {"schema_version":1,"mode":"advisory-refresh-plan","enabled":False,"season":season,
            "planned_at":iso(now),"source_observed_at":snapshot["retrieved_at"],"source_updated_at":snapshot["source_updated_at"],
            "horizon_days":horizon_days,"events":grouped,"missed_pregame_opportunities":overdue,
            "unconfirmed_kickoff_ids":missing,"limits":{"max_runs":32,"max_minutes_per_run":10,"max_acquisition_attempts":2},
            "policies":["Actual execution time replaces intended due time; post-kickoff forecasts are never backfilled.",
                        "Result polling requires observed verified FINAL; a kickoff-plus-hours event does not prove completion.",
                        "Meaningful source changes trigger an explicit rerun; no background polling is enabled.",
                        "Preserve verified same-season observations and forecast versions between runs.",
                        "Public scheduling/hosting and paid usage require owner approval."]}


def finalize_generation(current, completed_at):
    """Stamp completed computation, and suppress games crossing kickoff while scoring."""
    if completed_at < timestamp(current["as_of"]):
        raise ValueError("Generation completion cannot precede decision")
    current["generated_at"] = iso(completed_at)
    current["valid_until"] = iso(min(timestamp(current["source"]["source_updated_at"])+timedelta(hours=48),
                                     completed_at+timedelta(hours=24)))
    current["pipeline_sha256"]["ml/refresh.py"] = sha((ROOT/"ml/refresh.py").read_bytes())
    for game in current["games"]:
        game["generated_at"] = current["generated_at"]
        if game["status"] == "available" and timestamp(game["kickoff"]) <= completed_at:
            game.update(status="unavailable", reason="Kickoff passed during generation; no pregame probability issued",
                        home_probability=None, away_probability=None, factors=[], features={}, history={"home":[],"away":[]})
    return current


def refresh(snapshot_path=None, *, now=None, current_directory=None, operations_directory=None):
    """Build both outputs before promoting either; one verified snapshot drives both."""
    now_value = now or datetime.now(timezone.utc)
    season = current_season(now_value)
    check_season(season)
    path = Path(snapshot_path) if snapshot_path else acquire_bounded(season)
    snapshot = load_snapshot(path, season)
    # Online retrieval must happen before actual decision time. Fixed now is test-only.
    decision = now or datetime.now(timezone.utc)
    observations = snapshots_before(path, season, decision)
    if timestamp(snapshot["retrieved_at"]) > decision:
        raise ValueError("Decision cannot precede source observation")
    if observations and timestamp(observations[-1]["retrieved_at"]) > timestamp(snapshot["retrieved_at"]):
        raise ValueError("Selected snapshot is older than retained evidence; use the latest observation")
    prior = [s for s in observations if timestamp(s["retrieved_at"]) < timestamp(snapshot["retrieved_at"])]
    generated = now or datetime.now(timezone.utc)
    current = generate(snapshot, prior, iso(decision), iso(generated))
    generated = now or datetime.now(timezone.utc)
    current = finalize_generation(current, generated)
    digest = sha(canonical(current))
    filename = f"forecast-{season}-{digest}.json"
    forecasts = load_forecasts(season, current_directory)
    candidate = {"file":filename,"sha256":digest,"artifact":current}
    if not any(f["sha256"] == digest for f in forecasts):
        forecasts.append(candidate)
    operations = build_operations(forecasts, observations or [snapshot], iso(generated))
    display = [dict(game_id=game["id"], **select_display_forecast(current, game, operations, generated))
               for game in current["games"]]
    verify_publication_budget(current, operations)
    # Source/validation failures above leave both pointers unchanged. File-system
    # failures between these two replacements require rerun; no cross-file atomicity claim.
    current_path = publish_local(current, current_directory)
    operations_path = publish_operations(operations, operations_directory)
    return {"schema_version":1,"mode":"local-refresh-receipt","status":"complete","season":season,
            "snapshot":str(path),"source_raw_sha256":snapshot["raw_sha256"],"decision_at":iso(decision),"generated_at":iso(generated),
            "current_artifact":str(current_path),"operations_artifact":str(operations_path),
            "source_changed_since_previous": bool(prior and prior[-1]["raw_sha256"] != snapshot["raw_sha256"]),
            "available_forecasts":sum(g["status"]=="available" for g in current["games"]),
            "display_forecasts": display,
            "forecast_games":len(current["games"]),"publicly_published":False,"scheduler_enabled":False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", help="Verified current-season local snapshot; otherwise explicit acquisition")
    parser.add_argument("--plan", action="store_true", help="Print an advisory schedule only; requires a local snapshot")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    if args.plan:
        if not args.snapshot:
            parser.error("--plan requires --snapshot; planning does not fetch data or enable execution")
        snapshot = load_snapshot(args.snapshot, current_season(now))
        print(json.dumps(plan_refresh(snapshot, now),indent=2))
        return
    directory = ROOT / "artifacts/refresh"
    directory.mkdir(parents=True, exist_ok=True)
    try:
        with refresh_lock():
            receipt = refresh(args.snapshot)
    except Exception as error:
        receipt = {"status":"failed","observed_at":iso(datetime.now(timezone.utc)),"error_type":type(error).__name__,
                   "message":str(error)[:400],"scheduler_enabled":False,"publicly_published":False}
        (directory/f"failure-{sha(canonical(receipt))}.json").write_bytes(canonical(receipt))
        raise
    (directory/f"receipt-{sha(canonical(receipt))}.json").write_bytes(canonical(receipt))
    print(json.dumps(receipt,indent=2))


if __name__ == "__main__":
    main()
