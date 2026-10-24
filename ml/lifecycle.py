"""Offline prospective forecast archive and outcome reconciliation; no fitting or network."""
import argparse
import json
import math
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ml.data import ROOT
from ml.current import (MODEL_FREEZE_SHA, feature_state, frozen_model, observed_finals, schedule_key)
from ml.forecast import score as frozen_score
from ml.current_source import (EASTERN, FINAL, SCHEDULED, canonical, check_season,
                               iso, load_snapshot, sha, timestamp)

PROTOCOL = "forecast-lifecycle-v2"
HOME_RATE = 0.5572154167911563  # Saved 2010–2022 train mean, artifacts/evaluation.json.
HEX = re.compile(r"^[0-9a-f]{64}$")
IN_PROGRESS = {"IN_PROGRESS", "IN PROGRESS", "LIVE", "HALFTIME", "OVERTIME", "1", "2", "3", "4", "1ST QUARTER", "2ND QUARTER", "3RD QUARTER", "4TH QUARTER"}


def valid_result(game, observed_at):
    return (game["phase"] in FINAL and game["validated"] is True
            and all(type(game[key]) is int and 0 <= game[key] <= 200 for key in ("home_score", "away_score"))
            and game["kickoff"] is not None and game["day"] is not None
            and timestamp(game["kickoff"]) < timestamp(observed_at))


def status(game, observed_at, as_of=None):
    """A passed scheduled kickoff is not evidence that play actually began."""
    phase = game["phase"]
    decision = timestamp(as_of or observed_at)
    if phase in {"CANCELED", "CANCELLED"}:
        return "canceled"
    if phase in {"POSTPONED", "SUSPENDED", "DELAYED"}:
        return "postponed"
    if phase in FINAL:
        return "completed" if valid_result(game, observed_at) else "unknown"
    if phase in IN_PROGRESS:
        return "in_progress" if game["kickoff"] and timestamp(game["kickoff"]) < timestamp(observed_at) else "unknown"
    if phase in SCHEDULED and (not game["kickoff"] or timestamp(game["kickoff"]) > decision):
        return "scheduled"
    return "unknown"


def validate_snapshot(snapshot, generated):
    season = snapshot["season"]
    check_season(season)
    if not timestamp(snapshot["source_updated_at"]) <= timestamp(snapshot["retrieved_at"]) <= generated:
        raise ValueError("Invalid source observation ordering")
    if any(g["season"] != season or not g["id"].startswith(f"ngs-{season}-") for g in snapshot["games"]):
        raise ValueError("Mixed/protected seasons in reconciliation source")
    if len({g["id"] for g in snapshot["games"]}) != len(snapshot["games"]):
        raise ValueError("Duplicate source game ID")


def verify_forecast(bundle, season, generated):
    artifact = bundle["artifact"]
    if bundle["sha256"] != sha(canonical(artifact)) or bundle["file"] != f"forecast-{season}-{bundle['sha256']}.json":
        raise ValueError("Forecast content address mismatch")
    if artifact["season"] != season or artifact["mode"] != "current-forecast" or artifact["schema_version"] != 1:
        raise ValueError("Protected/mixed season or unsupported forecast")
    if artifact["model"] != frozen_model() or artifact["model_freeze_sha256"] != MODEL_FREEZE_SHA:
        raise ValueError("Forecast model does not match frozen incumbent")
    if timestamp(artifact["generated_at"]) > generated:
        raise ValueError("Future-dated forecast receipt")
    if len({g["id"] for g in artifact["games"]}) != len(artifact["games"]):
        raise ValueError("Duplicate forecast game ID")
    for game in artifact["games"]:
        if game["season"] != season or not game["id"].startswith(f"ngs-{season}-") or game["model_id"] != artifact["model"]["id"]:
            raise ValueError("Forecast game season/model mismatch")
        if game["generated_at"] != artifact["generated_at"]:
            raise ValueError("Forecast per-game generation mismatch")
        if game["status"] == "available":
            features = artifact["model"]["features"]
            if set(game["features"]) != set(features) or any(type(game["features"][f]) not in (int, float) or not math.isfinite(game["features"][f]) for f in features):
                raise ValueError("Invalid forecast feature values")
            z = artifact["model"]["intercept"] + sum(game["features"][f] * c for f, c in zip(features, artifact["model"]["coefficients"], strict=True))
            p = 1 / (1 + math.exp(-z)) if z >= 0 else math.exp(z) / (1 + math.exp(z))
            if [f.get("key") for f in game["factors"]] != features:
                raise ValueError("Forecast factor order mismatch")
            for f, coefficient in zip(game["factors"], artifact["model"]["coefficients"], strict=True):
                if (any(type(f.get(k)) not in (int, float) or not math.isfinite(f[k]) for k in ("home", "away", "difference", "coefficient", "contribution"))
                        or f["coefficient"] != coefficient or f["difference"] != game["features"][f["key"]]
                        or abs(f["home"]-f["away"]-f["difference"]) > 1e-12
                        or abs(f["contribution"]-f["difference"]*coefficient) > 1e-12):
                    raise ValueError("Forecast factor explanation mismatch")
            if (type(game["home_probability"]) not in (int, float) or type(game["away_probability"]) not in (int, float)
                    or not 0 <= game["home_probability"] <= 1 or not 0 <= game["away_probability"] <= 1
                    or abs(game["home_probability"] - p) > 1e-12 or abs(game["away_probability"] - (1-p)) > 1e-12):
                raise ValueError("Stored probability does not reproduce frozen model")
        elif game["status"] != "unavailable" or game["home_probability"] is not None or game["away_probability"] is not None:
            raise ValueError("Unavailable forecast contains invented probability")


def eligibility(game, artifact, scheduled):
    reasons = []
    if game["status"] != "available":
        reasons.append(game.get("reason") or "No probability was issued")
    if scheduled is None:
        reasons.append("Stable game ID missing from reconciliation source")
    elif any(game.get(k) != scheduled.get(k) for k in ("id", "season", "home", "away", "week", "day", "kickoff")) or game["schedule_fingerprint"] != schedule_key(scheduled):
        reasons.append("Schedule identity changed; a new pregame forecast is required")
    if not game["kickoff"] or not game["day"]:
        reasons.append("Kickoff date/time unconfirmed")
    else:
        kickoff, cutoff = timestamp(game["kickoff"]), timestamp(game["cutoff"])
        generated = timestamp(game["generated_at"])
        as_of = timestamp(artifact["as_of"])
        retrieved = timestamp(artifact["source"]["retrieved_at"])
        updated = timestamp(artifact["source"]["source_updated_at"])
        if not updated <= retrieved <= as_of <= generated < kickoff or not cutoff <= as_of:
            reasons.append("Forecast or source was not prospectively recorded before kickoff")
        midnight = datetime.fromisoformat(game["day"]).replace(tzinfo=EASTERN)
        if cutoff > midnight or timestamp(game["kickoff"]).astimezone(EASTERN).date().isoformat() != game["day"]:
            reasons.append("Prediction cutoff violates the frozen daily feature definition")
        if as_of - updated > timedelta(hours=48):
            reasons.append("Source was stale at the original forecast decision")
        for side in ("home", "away"):
            history = game["history"][side]
            if len({r["id"] for r in history}) != len(history):
                reasons.append("Duplicate historical result in feature state")
            for item in history:
                if (not item["id"].startswith(f"ngs-{game['season']}-") or item["id"] == game["id"]
                        or item["game_day"] >= game["day"] or timestamp(item["observed_at"]) >= cutoff
                        or not HEX.fullmatch(item["snapshot_sha256"])):
                    reasons.append("Feature history contains unavailable or future information")
                    break
    if game.get("source_phase") not in SCHEDULED:
        reasons.append("Original forecast schedule was not confirmed scheduled")
    if scheduled and scheduled["phase"] in {"CANCELLED", "CANCELED", "POSTPONED", "SUSPENDED", "DELAYED"}:
        reasons.append("Game is canceled or awaiting confirmed rescheduled kickoff")
    return list(dict.fromkeys(reasons))


def input_verification(game, artifact, snapshots):
    """Reproduce raw feature state from the exact captured input and claimed proofs."""
    if game["status"] != "available":
        return []
    captures = {sha(canonical(s)): s for s in snapshots}
    source = captures.get(artifact["snapshot_sha256"])
    if source is None:
        return ["Original input snapshot unavailable; feature state cannot be independently reproduced"]
    if {k: v for k, v in source.items() if k != "games"} != artifact["source"]:
        return ["Original source provenance does not match the forecast receipt"]
    target = next((g for g in source["games"] if g["id"] == game["id"]), None)
    if target is None or game["schedule_fingerprint"] != schedule_key(target):
        return ["Original schedule capture does not match the forecast receipt"]
    proof_ids = {proof["snapshot_sha256"] for side in ("home", "away") for proof in game["history"][side]}
    if not proof_ids <= set(captures):
        return ["Historical observation snapshot unavailable; feature state cannot be independently reproduced"]
    proofs = [captures[key] for key in sorted(proof_ids)]
    if any(timestamp(s["retrieved_at"]) > timestamp(source["retrieved_at"]) for s in proofs):
        return ["Historical observation was recorded after the original input capture"]
    try:
        evidence = observed_finals([*proofs, source], artifact["season"])
        row, history = feature_state(target, source["games"], evidence, timestamp(game["cutoff"]))
        probability, factors = frozen_score(artifact["model"], row)
        features = {key: row[key] for key in artifact["model"]["features"]}
        if (features != game["features"] or history != game["history"] or factors != game["factors"]
                or abs(probability-game["home_probability"]) > 1e-12):
            return ["Frozen feature state does not reproduce from the original source evidence"]
    except (ValueError, KeyError, TypeError) as error:
        return [f"Original input evidence cannot reproduce the forecast: {error}"]
    return []


def binary_score(p, y):
    observed_probability = p if y else 1-p
    loss = -math.log(min(1-1e-15, max(1e-15, observed_probability)))
    return {"correct": (p >= .5) == bool(y), "brier": (p-y)**2, "log_loss": loss, "surprise": loss}


def aggregate(rows):
    count = len(rows)
    return {"count": count, "accuracy": sum(r["correct"] for r in rows) / count if count else None,
            "brier": sum(r["brier"] for r in rows) / count if count else None,
            "log_loss": sum(r["log_loss"] for r in rows) / count if count else None}


def metric_set(rows, ties):
    result = {**aggregate(rows), "game_count": len({r["game_id"] for r in rows}), "ties_excluded": ties,
              "baselines": {name: aggregate([r["baseline"][name] for r in rows]) for name in ("coin_flip", "home_rate")},
              "by_season": [{"season": season, **aggregate([r for r in rows if r["season"] == season])} for season in sorted({r["season"] for r in rows})],
              "calibration": []}
    for i in range(10):
        selected = [r for r in rows if min(9, int(r["home_probability"]*10)) == i]
        n = len(selected)
        result["calibration"].append({"lower": i/10, "upper": (i+1)/10, "count": n,
            "mean_probability": sum(r["home_probability"] for r in selected)/n if n else None,
            "home_win_rate": sum(r["outcome_home"] for r in selected)/n if n else None,
            "brier": sum(r["brier"] for r in selected)/n if n else None})
    return result


def investigate(game, result, primary):
    reference = {"source_url": result["source_url"], "observed_at": result["observed_at"]}
    facts = [{"text": f"Verified final: {game['away']} {result['away_score']}, {game['home']} {result['home_score']}.", **reference}]
    hypotheses = []
    if primary:
        facts.append({"text": f"The recorded final pregame forecast assigned the home team {primary['home_probability']:.6f} probability; Brier score {primary['brier']:.6f} and surprise {primary['surprise']:.6f} nats.", **reference, "forecast_id": primary["forecast_id"]})
        if primary["surprise"] >= -math.log(.25):
            hypotheses.append({"text": "This low-probability result merits evidence review; random game variation remains a plausible explanation.",
                               "evidence_needed": "Verified play-by-play, turnovers, quarterback/roster availability and observed weather with publication timestamps; none is ingested by this adapter."})
    if result["tie"]:
        facts.append({"text": "The final was tied; the incumbent conditions on a non-tie, so binary scores are excluded.", **reference})
    if not primary and not result["tie"]:
        facts.append({"text": "No eligible recorded pregame forecast is available; no prediction score was invented.", **reference})
    hypotheses.append({"text": "Inputs absent from the incumbent may merit a separate challenger study; this result alone does not prove they would improve forecasts.",
                       "evidence_needed": "Prediction-time historical vintages, legitimate source rights, time-aware validation and comparison against the frozen incumbent."})
    return {"facts": facts, "hypotheses": hypotheses, "deficiencies": [],
            "limitations": ["Only schedule/result evidence is available. No causal attribution, player/news/weather claims, or demonstrated model defect follows from one game."],
            "agent_boundary": {"version": "bounded-investigation-v1", "mode": "deterministic-no-llm", "paid_calls": 0,
                "allowed_outputs": ["cited observed facts", "testable hypotheses", "missing-evidence requests"],
                "forbidden_actions": ["modify probabilities", "invent statistics", "rewrite artifacts", "fit or promote models", "access locked holdout"],
                "required_fact_fields": ["claim", "source_url", "published_at", "retrieved_at", "evidence_excerpt"]}}


def build_operations(forecasts, snapshots, generated_at):
    generated = timestamp(generated_at)
    if not snapshots:
        raise ValueError("Source unavailable: preserve the last successful operations artifact")
    for snapshot in snapshots:
        validate_snapshot(snapshot, generated)
    season = snapshots[0]["season"]
    if any(s["season"] != season for s in snapshots):
        raise ValueError("Mixed seasons in lifecycle operation")
    # Same-time contradictory observations have no defensible ordering.
    by_observation = {}
    for snapshot in snapshots:
        key = iso(timestamp(snapshot["retrieved_at"]))
        if key in by_observation and canonical(by_observation[key]) != canonical(snapshot):
            raise ValueError("Conflicting observations at the same timestamp")
        by_observation[key] = snapshot
    snapshots = sorted(by_observation.values(), key=lambda s: timestamp(s["retrieved_at"]))
    source = snapshots[-1]
    lookup = {g["id"]: g for g in source["games"]}
    catalog, receipt_sources = [], {}
    for bundle in sorted(forecasts, key=lambda f: f["file"]):
        verify_forecast(bundle, season, generated)
        artifact = bundle["artifact"]
        for game in artifact["games"]:
            identity = sha(canonical({"artifact_sha256": bundle["sha256"], "game_id": game["id"]}))
            exclusions = eligibility(game, artifact, lookup.get(game["id"]))
            exclusions.extend(input_verification(game, artifact, snapshots))
            row = {k: game[k] for k in ("home", "away", "season", "week", "day", "kickoff", "generated_at", "cutoff", "model_id", "features", "factors", "history", "home_probability", "away_probability")}
            row.update({"id": identity, "game_id": game["id"], "artifact_file": bundle["file"], "artifact_sha256": bundle["sha256"],
                        "valid_until": artifact["valid_until"], "forecast_status": game["status"], "eligible": not exclusions,
                        "exclusions": exclusions, "selected_final": False, "latest": False,
                        "source": artifact["source"], "snapshot_sha256": artifact["snapshot_sha256"],
                        "schedule_fingerprint": game["schedule_fingerprint"]})
            logical = sha(canonical({"game": game, "source": artifact["source"], "model": artifact["model"]}))
            if logical in receipt_sources:
                row["exclusions"].append("Duplicate forecast payload across packaging versions")
                row["eligible"] = False
            else:
                receipt_sources[logical] = identity
            catalog.append(row)
    if len({r["id"] for r in catalog}) != len(catalog):
        raise ValueError("Duplicate forecast artifact receipt")
    catalog.sort(key=lambda c: (timestamp(c["generated_at"]), c["id"]))
    games, evaluations, ties_primary, ties_all = [], [], 0, 0
    for game_id in sorted({r["game_id"] for r in catalog}):
        rows = [r for r in catalog if r["game_id"] == game_id]
        original, latest = rows[0], rows[-1]
        latest["latest"] = True
        scheduled = lookup.get(game_id)
        eligible = [r for r in rows if r["eligible"]]
        final = eligible[-1] if (eligible and scheduled and scheduled["kickoff"] and timestamp(scheduled["kickoff"]) <= generated
                                  and scheduled["phase"] not in {"POSTPONED", "SUSPENDED", "DELAYED", "CANCELED", "CANCELLED"}) else None
        if final:
            final["selected_final"] = True
        row = {"id": game_id, "home": (scheduled or latest)["home"], "away": (scheduled or latest)["away"], "season": season, "week": (scheduled or latest)["week"],
               "kickoff": scheduled["kickoff"] if scheduled else latest["kickoff"],
               "status": status(scheduled, source["retrieved_at"], generated_at) if scheduled else "unknown", "forecast_ids": [r["id"] for r in rows],
               "original_forecast_id": original["id"], "latest_forecast_id": latest["id"], "final_forecast_id": final["id"] if final else None,
               "result": None, "evaluations": [], "analysis": None}
        if scheduled and valid_result(scheduled, source["retrieved_at"]):
            result_data = {k: scheduled[k] for k in ("id", "season", "home", "away", "week", "day", "kickoff", "home_score", "away_score", "phase")}
            result_version = sha(canonical(result_data))
            observation = source
            for candidate in snapshots:
                previous = next((g for g in candidate["games"] if g["id"] == game_id), None)
                if previous and valid_result(previous, candidate["retrieved_at"]) and all(previous[k] == result_data[k] for k in result_data):
                    observation = candidate
                    break
            result = {"version": result_version, "home_score": scheduled["home_score"], "away_score": scheduled["away_score"],
                      "tie": scheduled["home_score"] == scheduled["away_score"], "observed_at": observation["retrieved_at"],
                      "source_url": observation["source_url"], "snapshot_sha256": sha(canonical(observation)), "raw_sha256": observation["raw_sha256"]}
            row["result"] = result
            if result["tie"]:
                ties_primary += int(final is not None)
                ties_all += len(eligible)
            else:
                y = int(result["home_score"] > result["away_score"])
                for forecast in eligible:
                    p = forecast["home_probability"]
                    score = {"forecast_id": forecast["id"], "game_id": game_id, "season": season, "primary": forecast is final,
                             "home_probability": p, "outcome_home": y, **binary_score(p, y),
                             "baseline": {"coin_flip": {"probability": .5, **binary_score(.5, y)}, "home_rate": {"probability": HOME_RATE, **binary_score(HOME_RATE, y)}}}
                    row["evaluations"].append(score)
                    evaluations.append(score)
            row["analysis"] = investigate(scheduled, result, next((e for e in row["evaluations"] if e["primary"]), None))
        games.append(row)
    schedule = [{**{k: g[k] for k in ("id", "season", "week", "home", "away", "kickoff", "day", "stadium")},
                 "status": status(g, source["retrieved_at"], generated_at), "source_phase": g["phase"]} for g in source["games"]]
    warnings = []
    if generated - timestamp(source["source_updated_at"]) > timedelta(hours=48):
        warnings.append("The latest source update is over 48 hours old; outcomes and schedule statuses may be stale. No fresh source receipt was invented.")
    if not evaluations:
        warnings.append("No eligible recorded forecasts have an observed non-tied final result; prospective metrics remain unavailable.")
    return {"schema_version": 1, "mode": "forecast-operations", "season": season, "generated_at": iso(generated),
            "model_id": frozen_model()["id"], "model_freeze_sha256": MODEL_FREEZE_SHA,
            "protocol": {"version": PROTOCOL, "sha256": sha((ROOT / "docs/LIFECYCLE_PROTOCOL.md").read_bytes())},
            "pipeline_sha256": {"ml/lifecycle.py": sha((ROOT / "ml/lifecycle.py").read_bytes())},
            "source": {**{k: source[k] for k in ("retrieved_at", "source_updated_at", "source_url", "raw_sha256")}, "snapshot_sha256": sha(canonical(source))},
            "schedule": schedule, "schedule_counts": dict(Counter(g["status"] for g in schedule)), "catalog": catalog, "games": games,
            "metrics": {"primary": metric_set([e for e in evaluations if e["primary"]], ties_primary), "all_snapshots": metric_set(evaluations, ties_all)},
            "warnings": warnings,
            "limitations": ["Prospective performance is separate from retrospective 2023 validation and the locked 2024–2025 holdout.",
                "All-snapshot scores include correlated predictions of the same game; use final-per-game scores as the headline.",
                "Final selection uses time and schedule identity only, never the outcome. Historical display expiry does not erase a pregame record.",
                "No player, injury, weather or play-by-play research is ingested; postgame interpretation is deterministic and explicitly bounded.",
                "This static receipt does not prove live schedule status or exact game completion time. Source corrections can change later evaluation versions."]}


def publish_operations(artifact, directory=None):
    directory = Path(directory or ROOT / "web/public/data/operations")
    directory.mkdir(parents=True, exist_ok=True)
    body = canonical(artifact)
    digest = sha(body)
    name = f"operations-{digest}.json"
    target = directory / name
    if target.exists() and target.read_bytes() != body:
        raise ValueError("Operations version collision")
    if not target.exists():
        target.write_bytes(body)
    pointer = {"schema_version": 1, "file": name, "sha256": digest, "generated_at": artifact["generated_at"], "season": artifact["season"]}
    temporary = directory / ".latest.tmp"
    temporary.write_bytes(canonical(pointer))
    temporary.replace(directory / "latest.json")
    return target


def load_forecasts(season, directory=None):
    check_season(season)
    directory = Path(directory or ROOT / "web/public/data/current")
    forecasts = []
    for path in sorted(directory.glob(f"forecast-{season}-*.json")):
        body = path.read_bytes()
        if path.name != f"forecast-{season}-{sha(body)}.json":
            raise ValueError("Forecast archive checksum mismatch")
        forecasts.append({"file": path.name, "sha256": sha(body), "artifact": json.loads(body)})
    return forecasts


def export_operations(snapshot, *, forecast_directory=None, output_directory=None, generated_at=None, prior_snapshots=()):
    season = snapshot["season"]
    forecasts = load_forecasts(season, forecast_directory)
    now = generated_at or iso(datetime.now(timezone.utc))
    supplied = {sha(canonical(s)): s for s in [*prior_snapshots, snapshot]}
    needed = {b["artifact"]["snapshot_sha256"] for b in forecasts}
    needed.update(proof["snapshot_sha256"] for b in forecasts for g in b["artifact"]["games"]
                  for side in ("home", "away") for proof in g["history"][side])
    for digest in sorted(needed - set(supplied)):
        if not HEX.fullmatch(digest):
            raise ValueError("Invalid archived source digest")
        path = ROOT / "data/current" / str(season) / f"snapshot-{digest}.json"
        if path.exists():
            supplied[digest] = load_snapshot(path, season)
    artifact = build_operations(forecasts, list(supplied.values()), now)
    return publish_operations(artifact, output_directory)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, help="Existing verified season-specific capture; no acquisition occurs")
    parser.add_argument("--season", required=True, type=int)
    parser.add_argument("--generated-at", help="Actual observation time, or explicit reproducibility timestamp")
    args = parser.parse_args()
    check_season(args.season)
    snapshot = load_snapshot(args.snapshot, args.season)
    prior = [load_snapshot(p, args.season) for p in Path(args.snapshot).parent.glob("snapshot-*.json") if p.resolve() != Path(args.snapshot).resolve()]
    path = export_operations(snapshot, prior_snapshots=prior, generated_at=args.generated_at)
    artifact = json.loads(path.read_bytes())
    print(json.dumps({"artifact": str(path), "season": artifact["season"], "receipts": len(artifact["catalog"]), "forecasted_games": len(artifact["games"]), "scored_games": artifact["metrics"]["primary"]["count"]}))


if __name__ == "__main__":
    main()
