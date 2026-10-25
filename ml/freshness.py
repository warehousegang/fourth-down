"""Display policy for verified archives; never computes or refreshes a probability.

Call only after build_operations has reproduced archived inputs and eligibility.
Source age limits NEW inference. It does not erase a valid original prediction.
"""
from ml.current_source import SCHEDULED, timestamp

SOURCE_STALE_REASON = "Source is over 48 hours old; refresh before using forecasts"


def select_display_forecast(current, game, operations, now):
    def blocked(reason):
        return {"state": "unavailable", "forecast_id": None, "reason": reason}

    if not operations:
        return blocked("Verified forecast history is unavailable.")
    if timestamp(current["generated_at"]) > now or timestamp(operations["generated_at"]) > now:
        return blocked("Forecast evidence is dated in the future.")
    if not game["kickoff"]:
        return blocked("Kickoff is unconfirmed; no eligible pregame prediction is displayed.")
    if (operations["season"] != current["season"]
            or timestamp(operations["source"]["retrieved_at"]) < timestamp(current["source"]["retrieved_at"])):
        return blocked("Forecast and latest source evidence do not match.")
    scheduled = next((g for g in operations["schedule"] if g["id"] == game["id"]), None)
    identity = ("home", "away", "kickoff", "day", "week", "season")
    if not scheduled or any(scheduled[k] != game[k] for k in identity):
        return blocked("The observed schedule changed; inspect the retained forecast history.")
    if scheduled["status"] in {"postponed", "canceled"}:
        return blocked("The game is postponed or canceled; earlier forecasts remain in Forecast History.")
    archived = now >= timestamp(game["kickoff"])
    if not archived:
        if scheduled["status"] != "scheduled" or game["source_phase"] not in SCHEDULED:
            return blocked("The matchup is not confirmed scheduled.")
        if "schedule_fingerprint" not in game:
            return blocked("No current pregame decision is available; inspect Forecast History.")
        if game["status"] != "available" and game["reason"] != SOURCE_STALE_REASON:
            return blocked(game["reason"] or "Required forecast inputs are unavailable.")
        if operations["source"]["raw_sha256"] != current["source"]["raw_sha256"]:
            return blocked("Forecast and latest source evidence do not match.")
    candidates = [f for f in operations["catalog"] if (
        f["game_id"] == game["id"] and f["eligible"] and not f["exclusions"]
        and f["forecast_status"] == "available"
        and all(f[k] == game[k] for k in identity)
        and (archived or (f["schedule_fingerprint"] == game["schedule_fingerprint"]
                         and f["source"]["raw_sha256"] == current["source"]["raw_sha256"]))
        and timestamp(f["generated_at"]) <= now
        and timestamp(f["generated_at"]) < timestamp(game["kickoff"]))]
    if not candidates:
        return blocked("No eligible forecast with verified unchanged inputs is available.")
    record = max(candidates, key=lambda f: (timestamp(f["generated_at"]), f["id"]))
    final_id = next((g["final_forecast_id"] for g in operations["games"] if g["id"] == game["id"]), None)
    if archived and final_id:
        record = next((f for f in candidates if f["id"] == final_id), None)
        if record is None:
            return blocked("No eligible forecast with verified unchanged inputs is available.")
    if archived:
        return {"state": "archived", "forecast_id": record["id"], "reason": None}
    older = now >= timestamp(record["valid_until"]) or record["generated_at"] != current["generated_at"]
    return {"state": "older" if older else "fresh", "forecast_id": record["id"], "reason": None}
