"""Current-week inference only. No training imports or protected-season pathway."""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ml.data import ROOT
from ml.features import FEATURES, VERSION, Record
from ml.forecast import score
from ml.current_source import (EASTERN, FINAL, SCHEDULED, acquire, canonical, check_season,
                               current_season, iso, load_snapshot, sha, timestamp)

MODEL_FREEZE_SHA = "2896a526ed8035b1674a6beb3c8d27c76ba4b3f466309bfeb729c6ddbf80f957"
MAX_AGE = timedelta(hours=48)


def frozen_model():
    body = (ROOT / "docs/FROZEN_MODEL.json").read_bytes()
    if sha(body) != MODEL_FREEZE_SHA:
        raise ValueError("Original candidate freeze changed")
    freeze = json.loads(body)
    for path, expected in freeze["file_sha256"].items():
        if sha((ROOT / path).read_bytes()) != expected:
            raise ValueError(f"Frozen source changed: {path}")
    model = freeze["model"]
    if model["features"] != FEATURES or model["feature_version"] != VERSION:
        raise ValueError("Feature definition mismatch")
    return model


def result_key(game):
    return sha(canonical({k: game[k] for k in ("id", "season", "home", "away", "day", "kickoff", "phase", "home_score", "away_score", "validated")}))


def schedule_key(game):
    return sha(canonical({k: game[k] for k in ("id", "home", "away", "day", "kickoff", "week")}))


def completed(game):
    return (game["phase"] in FINAL and game["validated"] and game["home_score"] is not None
            and game["away_score"] is not None and game["day"] is not None and game["kickoff"] is not None)


def observed_finals(snapshots, season):
    evidence = {}
    for snapshot in snapshots:
        if snapshot["season"] != season or any(g["season"] != season for g in snapshot["games"]):
            raise ValueError("Mixed/protected season in state evidence")
        observed = timestamp(snapshot["retrieved_at"])
        for game in snapshot["games"]:
            if completed(game) and timestamp(game["kickoff"]) < observed:
                key = result_key(game)
                if key not in evidence or observed < timestamp(evidence[key]["observed_at"]):
                    evidence[key] = {"observed_at": iso(observed), "snapshot_sha256": sha(canonical(snapshot))}
    return evidence


def feature_state(target, games, evidence, cutoff):
    """Reuse frozen Record.values; explicitly build only eligible chronological records."""
    day = datetime.fromisoformat(target["day"]).date()
    values, history = {}, {"home": [], "away": []}
    for side in ("home", "away"):
        team = target[side]
        record = Record()
        for game in sorted(games, key=lambda g: (g["day"] or "9999", g["id"])):
            if game["season"] != target["season"]:
                raise ValueError("Cross-season state is forbidden")
            if game["id"] == target["id"] or team not in (game["home"], game["away"]) or game["phase"] == "CANCELLED":
                continue
            if not game["day"]:
                if game["week"] < target["week"]:
                    raise ValueError(f"Unknown date for earlier {team} game {game['id']}")
                continue
            played = datetime.fromisoformat(game["day"]).date()
            if played >= day:
                continue  # Frozen feature rule: no current-day or future-day results.
            if game["kickoff"] and timestamp(game["kickoff"]) >= cutoff:
                # Known earlier-date game has not started as of this early forecast.
                raise ValueError(f"Intervening {team} game {game['id']} not completed before cutoff")
            proof = evidence.get(result_key(game))
            if not completed(game) or proof is None or timestamp(proof["observed_at"]) >= cutoff:
                raise ValueError(f"Final result for {team} game {game['id']} not confirmed before cutoff")
            margin = (game["home_score"] - game["away_score"]) * (1 if team == game["home"] else -1)
            record.wins += 1 if margin > 0 else .5 if margin == 0 else 0
            record.games += 1
            record.margins.append(float(margin))
            record.last = played
            history[side].append({"id": game["id"], "game_day": game["day"], **proof})
        values[side] = record.values(day)
    row = {f"{side}_{key}": value for side, v in values.items() for key, value in v.items()}
    for key in FEATURES:
        name = key.removesuffix("_diff")
        row[key] = values["home"][name] - values["away"][name]
    return row, history


def generate(snapshot, prior_snapshots, as_of, generated_at=None):
    season = snapshot["season"]
    check_season(season)
    model = frozen_model()
    as_of = timestamp(as_of)
    generated = timestamp(generated_at) if generated_at else datetime.now(timezone.utc)
    retrieved = timestamp(snapshot["retrieved_at"])
    updated = timestamp(snapshot["source_updated_at"])
    if not updated <= retrieved <= as_of <= generated or current_season(as_of) != season:
        raise ValueError("Invalid forecast/source time ordering or season")
    games = snapshot["games"]
    if any(g["season"] != season for g in games):
        raise ValueError("Mixed/protected season in current input")
    evidence = observed_finals([*prior_snapshots, snapshot], season)
    old = {g["id"]: g for s in sorted(prior_snapshots, key=lambda s: s["retrieved_at"]) for g in s["games"]}
    future = sorted((g for g in games if g["kickoff"] and timestamp(g["kickoff"]) > as_of
                     and g["phase"] not in FINAL | {"CANCELLED"}), key=lambda g: g["kickoff"])
    week = future[0]["week"] if future else None
    unresolved = [g["week"] for g in games if not g["kickoff"] and g["phase"] in SCHEDULED]
    # A missing kickoff in this week must not silently advance the screen to next week.
    if unresolved:
        week = min([*unresolved, *([week] if week is not None else [])])
    if week is None:
        pending = [g["week"] for g in games if g["phase"] in {"POSTPONED", "SUSPENDED"}]
        week = min(pending) if pending else None
    output = []
    for g in sorted(games, key=lambda g: (g["kickoff"] or "9999", g["id"])):
        pending_old = g["phase"] in {"POSTPONED", "SUSPENDED"} and week is not None and g["week"] <= week
        if g["week"] != week and not pending_old:
            continue
        if g["phase"] in FINAL | {"CANCELLED"}:
            continue
        if g["kickoff"] and timestamp(g["kickoff"]) <= as_of and not pending_old:
            continue  # Already started: never call it an upcoming prediction.
        cutoff = min(as_of, datetime.fromisoformat(g["day"]).replace(tzinfo=EASTERN)) if g["day"] else as_of
        item = {k: g[k] for k in ("id", "source_game_id", "season", "week", "home", "away", "kickoff", "stadium", "day")}
        item.update({"cutoff": iso(cutoff), "generated_at": iso(generated), "model_id": model["id"],
                     "schedule_fingerprint": schedule_key(g), "status": "unavailable", "reason": None,
                     "home_probability": None, "away_probability": None, "factors": [], "features": {},
                     "history": {"home": [], "away": []}, "warnings": [], "source_phase": g["phase"]})
        if g["id"] in old and schedule_key(old[g["id"]]) != schedule_key(g):
            item["warnings"].append("Schedule changed since the previous snapshot; this version uses the revised date and kickoff.")
        try:
            if as_of - updated > MAX_AGE:
                raise ValueError("Source is over 48 hours old; refresh before using forecasts")
            if not g["day"] or not g["kickoff"]:
                raise ValueError("Kickoff date/time unconfirmed; no probability generated")
            if g["phase"] not in SCHEDULED:
                raise ValueError(f"Game status {g['phase']} is not confirmed scheduled")
            if timestamp(g["kickoff"]) <= generated:
                raise ValueError("Kickoff passed during generation; no pregame probability issued")
            row, history = feature_state(g, games, evidence, cutoff)
            probability, factors = score(model, row)
            item.update(status="available", home_probability=probability, away_probability=1-probability,
                        factors=factors, features={key: row[key] for key in FEATURES}, history=history)
            if min(row["home_games"], row["away_games"]) < 3:
                item["warnings"].append("Limited current-season history; frozen priors apply. No prior-season strength is used.")
        except ValueError as error:
            item["reason"] = str(error)
        output.append(item)
    return {"schema_version": 1, "mode": "current-forecast", "season": season, "week": week,
            "as_of": iso(as_of), "generated_at": iso(generated), "valid_until": iso(min(updated + MAX_AGE, generated + timedelta(hours=24))),
            "model": model, "model_freeze_sha256": MODEL_FREEZE_SHA,
            "pipeline_sha256": {p: sha((ROOT/p).read_bytes()) for p in ("ml/current.py", "ml/current_source.py")},
            "source": {k: v for k, v in snapshot.items() if k != "games"},
            "snapshot_sha256": sha(canonical(snapshot)), "games": output,
            "warnings": (["Source update is over 24 hours old; refresh before kickoff."] if as_of-updated > timedelta(hours=24) else []),
            "limitations": ["Frozen model trained on 2010–2022 and selected on 2023; current-season predictive performance is not established.",
                            "Only current-season wins, scoring margins, recent margins and rest differences affect probabilities.",
                            "No injuries, player news, quarterbacks, weather, odds or prior-season strength inputs.",
                            "Probabilities condition on a non-tied outcome; designated home advantage applies even at neutral venues.",
                            "Final results are known by snapshot observation time, not an invented exact completion timestamp.",
                            "Manual static snapshot; schedules may change after retrieval. Earlier-day cutoff can make predictions unavailable."]}


def publish_local(artifact, directory=None):
    directory = Path(directory or ROOT / "web/public/data/current")
    directory.mkdir(parents=True, exist_ok=True)
    body = canonical(artifact)
    digest = sha(body)
    name = f"forecast-{artifact['season']}-{digest}.json"
    version = directory / name
    if version.exists() and version.read_bytes() != body:
        raise ValueError("Version collision")
    if not version.exists():
        version.write_bytes(body)
    pointer = {"schema_version": 1, "file": name, "sha256": digest,
               "generated_at": artifact["generated_at"], "season": artifact["season"]}
    temporary = directory / ".latest.tmp"
    temporary.write_bytes(canonical(pointer))
    temporary.replace(directory / "latest.json")
    return version


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", help="Existing current-season snapshot for offline reproduction; otherwise fetch explicitly")
    parser.add_argument("--as-of", help="Timezone-aware decision time; cannot precede source observation")
    parser.add_argument("--generated-at", help="Fixed timestamp for exact offline reproduction")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    season = current_season(timestamp(args.as_of) if args.as_of else now)
    check_season(season)
    path = Path(args.snapshot) if args.snapshot else acquire(season)
    snapshot = load_snapshot(path, season)
    cutoff = args.as_of or iso(datetime.now(timezone.utc))
    previous = []
    for p in sorted(path.parent.glob("snapshot-*.json")):
        if p.resolve() == path.resolve():
            continue
        other = load_snapshot(p, season)
        if timestamp(other["retrieved_at"]) < timestamp(snapshot["retrieved_at"]):
            previous.append(other)
    artifact = generate(snapshot, previous, cutoff, args.generated_at)
    output = publish_local(artifact)
    print(json.dumps({"artifact": str(output), "snapshot": str(path), "season": season, "week": artifact["week"],
                      "available": sum(g["status"] == "available" for g in artifact["games"]), "games": len(artifact["games"])}))


if __name__ == "__main__":
    main()
