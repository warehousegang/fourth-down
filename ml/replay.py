"""Independent event-time retrospective validation; no fitting, network or public writes."""
import argparse
import csv
import hashlib
import io
import json
import math
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ("smooth_win_diff", "margin_diff", "recent_margin_diff", "rest_diff")
SOURCE_SHA = "20f573837dac7d9ea41dade07b165de6164b3370d60e49d5242e5255cabb7d01"
FREEZE_SHA = "2896a526ed8035b1674a6beb3c8d27c76ba4b3f466309bfeb729c6ddbf80f957"
DEMO_SHA = "41c3ad0d8d2997238b464f196b700ce328f38eb6e93831a18d504c7ef6aa24a9"
EASTERN = ZoneInfo("America/New_York")
SEED, REPLICATES = 42, 2000


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def parse_rows(raw):
    """Season validation is a separate first pass, before any outcome parsing."""
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    required = {"game_id", "season", "week", "game_type", "gameday", "gametime", "home_team", "away_team", "home_score", "away_score"}
    if not required <= set(reader.fieldnames or []):
        raise ValueError("Missing replay source columns")
    text_rows = list(reader)
    if not text_rows or any(row["season"] not in {str(n) for n in range(2010, 2024)} for row in text_rows):
        raise ValueError("Protected or unsupported season; only 2010–2023 is authorized")
    rows, seen = [], set()
    for original in text_rows:
        row = dict(original)
        if row["game_type"] != "REG":
            raise ValueError("Replay source must contain regular-season games only")
        if not row["game_id"] or row["game_id"] in seen:
            raise ValueError("Missing or duplicate replay game identity")
        seen.add(row["game_id"])
        if not row["home_team"] or not row["away_team"] or row["home_team"] == row["away_team"]:
            raise ValueError("Invalid replay team identity")
        row["season"] = int(row["season"])
        if row["week"] not in {str(w) for w in range(1, 19)}:
            raise ValueError("Invalid replay week")
        row["week"] = int(row["week"])
        row["day"] = date.fromisoformat(row["gameday"])
        if not date(row["season"], 8, 1) <= row["day"] <= date(row["season"] + 1, 2, 28):
            raise ValueError("Date outside declared regular season")
        for key in ("home_score", "away_score"):
            value = row[key]
            if value == "":
                row[key] = None
            elif not value.isdigit() or not 0 <= int(value) <= 200:
                raise ValueError("Invalid replay score")
            else:
                row[key] = int(value)
        row["complete"] = row["home_score"] is not None and row["away_score"] is not None
        rows.append(row)
    return sorted(rows, key=lambda row: (row["season"], row["day"], row["game_id"]))


def read_approved_source(path=None, manifest_path=None):
    path = Path(path or ROOT / "data/schedules-2010-2023.csv")
    manifest_path = Path(manifest_path or ROOT / "data/manifest.json")
    raw = path.read_bytes()
    manifest = json.loads(manifest_path.read_bytes())
    if digest(raw) != SOURCE_SHA or manifest["sha256"] != SOURCE_SHA:
        raise ValueError("Replay source checksum differs from the frozen approved dataset")
    rows = parse_rows(raw)
    if len(rows) != manifest["rows"] or {row["season"] for row in rows} != set(range(2010, 2024)):
        raise ValueError("Replay source coverage differs from its approved manifest")
    return rows, manifest


def frozen_evidence():
    freeze_raw = (ROOT / "docs/FROZEN_MODEL.json").read_bytes()
    demo_raw = (ROOT / "web/public/data/demo.json").read_bytes()
    if digest(freeze_raw) != FREEZE_SHA or digest(demo_raw) != DEMO_SHA:
        raise ValueError("Protected frozen evidence checksum mismatch")
    freeze, demo = json.loads(freeze_raw), json.loads(demo_raw)
    checks = {name: digest((ROOT / name).read_bytes()) == expected for name, expected in freeze["file_sha256"].items()}
    if not all(checks.values()) or freeze["model"] != demo["model"]:
        raise ValueError("Frozen source or model changed")
    model = freeze["model"]
    if (model["id"] != "schedule-v1-741cf41752" or tuple(model["features"]) != FEATURES or model["train_seasons"] != [2010, 2022]
            or len(model["coefficients"]) != 4 or freeze["holdout_approval"] is not None or freeze["holdout_evaluated"] is not False):
        raise ValueError("Frozen model configuration or holdout boundary changed")
    return model, demo, checks


def reconstruct(rows, target, model):
    if type(target["season"]) is not int or not 2010 <= target["season"] <= 2023 or any(type(r["season"]) is not int or not 2010 <= r["season"] <= 2023 for r in rows):
        raise ValueError("Protected or unsupported replay season")
    if tuple(model["features"]) != FEATURES or len(model["coefficients"]) != len(FEATURES):
        raise ValueError("Replay requires the exact frozen feature order")
    side_values, histories = {}, {}
    for side in ("home", "away"):
        club = target[side + "_team"]
        history = sorted((row for row in rows if row["season"] == target["season"] and row["day"] < target["day"]
                          and row["complete"] and club in (row["home_team"], row["away_team"])),
                         key=lambda row: (row["day"], row["game_id"]))
        margins = [(row["home_score"] - row["away_score"]) * (1 if row["home_team"] == club else -1) for row in history]
        n = len(margins)
        wins = sum(1 if value > 0 else .5 if value == 0 else 0 for value in margins)
        side_values[side] = {"smooth_win_diff": (wins + 2) / (n + 4), "margin_diff": sum(margins) / (n + 4),
                             "recent_margin_diff": sum(margins[-5:]) / (min(5, n) + 2),
                             "rest_diff": min(14, (target["day"] - history[-1]["day"]).days) if n else 7}
        histories[side] = [{"id": row["game_id"], "gameday": row["gameday"]} for row in history]
    factors, z = [], model["intercept"]
    for key, coefficient in zip(FEATURES, model["coefficients"], strict=True):
        home, away = side_values["home"][key], side_values["away"][key]
        difference = home - away
        contribution = difference * coefficient
        factors.append({"key": key, "home": home, "away": away, "difference": difference,
                        "coefficient": coefficient, "contribution": contribution})
        z += contribution
    if not math.isfinite(z):
        raise ValueError("Non-finite replay probability input")
    probability = 1 / (1 + math.exp(-z)) if z >= 0 else math.exp(z) / (1 + math.exp(z))
    cutoff = datetime.combine(target["day"], datetime.min.time(), tzinfo=EASTERN)
    kickoff = datetime.fromisoformat(target["gameday"] + "T" + target["gametime"]).replace(tzinfo=EASTERN) if target["gametime"] else None
    if kickoff and kickoff < cutoff:
        raise ValueError("Historical kickoff precedes its daily cutoff")
    return {"id": target["game_id"], "season": target["season"], "week": target["week"], "gameday": target["gameday"],
            "home": target["home_team"], "away": target["away_team"], "cutoff": cutoff.isoformat(),
            "kickoff": kickoff.isoformat() if kickoff else None, "model_id": model["id"], "history": histories,
            "features": {f["key"]: f["difference"] for f in factors}, "factors": factors,
            "home_probability": probability, "historical_publication_availability_proven": False}


def scores(outcomes, probabilities):
    y, p = np.asarray(outcomes, dtype=int), np.asarray(probabilities, dtype=float)
    if not len(y) or len(y) != len(p) or not np.isin(y, [0, 1]).all() or not np.isfinite(p).all() or (p < 0).any() or (p > 1).any():
        raise ValueError("Invalid binary scoring observations")
    loss_p = np.clip(p, np.finfo(float).eps, 1 - np.finfo(float).eps)
    return {"n": len(y), "accuracy": float(np.mean((p >= .5) == y)), "brier": float(np.mean((p - y) ** 2)),
            "log_loss": float(np.mean(-(y * np.log(loss_p) + (1-y) * np.log1p(-loss_p))))}


def reliability(outcomes, probabilities):
    y, p = np.asarray(outcomes), np.asarray(probabilities)
    buckets = np.minimum((p * 10).astype(int), 9)
    return [{"bin": i, "lower": i / 10, "upper": (i+1) / 10, "count": int((buckets == i).sum()),
             "predicted": float(p[buckets == i].mean()), "observed": float(y[buckets == i].mean())}
            for i in range(10) if (buckets == i).any()]


def block_intervals(outcomes, probabilities, home_rate, blocks):
    y, p = np.asarray(outcomes), np.asarray(probabilities)
    p_loss = np.clip(p, np.finfo(float).eps, 1-np.finfo(float).eps)
    vectors = {"accuracy": ((p >= .5) == y).astype(float), "brier": (p-y)**2,
               "log_loss": -(y*np.log(p_loss)+(1-y)*np.log1p(-p_loss)),
               "brier_difference_home": (p-y)**2-(home_rate-y)**2,
               "brier_difference_coin": (p-y)**2-(.5-y)**2}
    unique = sorted(set(blocks))
    groups = [np.asarray([i for i, key in enumerate(blocks) if key == block]) for block in unique]
    rng = np.random.default_rng(SEED)
    draws = {name: [] for name in vectors}
    for _ in range(REPLICATES):
        selected = np.concatenate([groups[i] for i in rng.integers(len(groups), size=len(groups))])
        for name, values in vectors.items():
            draws[name].append(float(values[selected].mean()))
    return {"unit": "season-week", "blocks": [list(value) for value in unique], "block_count": len(unique),
            "replicates": REPLICATES, "seed": SEED, "method": "paired percentile bootstrap; complete week blocks",
            "intervals": {name: {"estimate": float(vector.mean()), "low": float(np.quantile(draws[name], .025)),
                                  "high": float(np.quantile(draws[name], .975))} for name, vector in vectors.items()}}


def compare_saved(reconstructed, saved):
    errors = []
    for key in ("id", "season", "week", "home", "away", "model_id", "cutoff", "kickoff"):
        if reconstructed[key] != saved[key]:
            errors.append("identity/timestamp:" + key)
    for side in ("home", "away"):
        if len(reconstructed["history"][side]) != saved["history_games"][side]:
            errors.append("history_count:" + side)
    if saved["status"] != "available" or len(saved["factors"]) != len(FEATURES):
        errors.append("missing_saved_probability_or_factors")
        return errors
    for expected, actual in zip(reconstructed["factors"], saved["factors"], strict=True):
        for key, value in expected.items():
            if (key == "key" and actual.get(key) != value) or (key != "key" and (type(actual.get(key)) not in (float, int) or not math.isfinite(actual[key]) or abs(actual[key]-value) > 1e-12)):
                errors.append("factor:" + expected["key"] + ":" + key)
    if type(saved["home_probability"]) not in (float,int) or not math.isfinite(saved["home_probability"]) or abs(saved["home_probability"]-reconstructed["home_probability"]) > 1e-12:
        errors.append("probability")
    return errors


def verify_saved_challenger():
    directory = ROOT / "web/public/data/research"
    pointer = json.loads((directory / "latest.json").read_bytes())
    name, expected = pointer["file"], pointer["sha256"]
    if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected) or name != "challenger-" + expected + ".json":
        raise ValueError("Unsafe research artifact pointer")
    raw = (directory / name).read_bytes()
    if digest(raw) != expected:
        raise ValueError("Saved research artifact checksum mismatch")
    artifact = json.loads(raw)
    if artifact["status"] != "research-only-not-promoted" or artifact["promotion"]["eligible"] is not False:
        raise ValueError("Saved research promotion boundary changed")
    models = {f["season"]: f["model"] for f in artifact["fold_models"]}
    if set(models) != set(range(2018, 2024)) or len(artifact["fold_models"]) != 6:
        raise ValueError("Saved challenger fold coverage changed")
    if any(type(row["season"]) is not int or row["season"] not in models for row in artifact["predictions"]):
        raise ValueError("Protected or unsupported saved challenger season")
    by_season, largest = [], 0.0
    for season, model in sorted(models.items()):
        if not (model["fit_seasons"][0] == 2011 and model["fit_seasons"][1] == season - 2 and model["calibration"]["season"] == season - 1):
            raise ValueError("Saved challenger chronological boundary violated")
        held = [row for row in artifact["predictions"] if row["season"] == season]
        probabilities = []
        for row in held:
            z = model["intercept"] + sum(row["features"][key] * coefficient for key, coefficient in zip(model["features"], model["coefficients"], strict=True))
            z = model["calibration"]["intercept"] + model["calibration"]["coefficient"] * z
            p = 1/(1+math.exp(-z))
            largest = max(largest, abs(p-row["probabilities"]["challenger"]))
            if abs(p-row["probabilities"]["challenger"]) > 1e-12:
                raise ValueError("Saved challenger probability arithmetic differs")
            probabilities.append(p)
        recomputed = scores([r["home_win"] for r in held], probabilities)
        original = next(f for f in artifact["evaluation"]["backtests"] if f["season"] == season)["metrics"]["challenger"]
        if any(abs(recomputed[k]-original[k]) > 1e-12 for k in recomputed):
            raise ValueError("Saved challenger metric arithmetic differs")
        by_season.append({"season": season, "fit_seasons": model["fit_seasons"], "calibration_season": season - 1, "metrics": recomputed})
    return {"artifact_sha256": expected, "model_id": artifact["model"]["id"], "predictions_checked": len(artifact["predictions"]),
            "largest_probability_error": largest, "chronological_splits_verified": True, "by_season": by_season,
            "scope": "Saved prediction arithmetic and split metadata only; no fitting or independent training reproduction",
            "prospective_or_untouched_test": False}


def replay():
    rows, manifest = read_approved_source()
    model, demo, checks = frozen_evidence()
    targets = [row for row in rows if row["season"] == 2023 and row["complete"] and row["home_score"] != row["away_score"]]
    training = [row for row in rows if row["season"] <= 2022 and row["complete"] and row["home_score"] != row["away_score"]]
    home_rate = sum(r["home_score"] > r["away_score"] for r in training) / len(training)
    if len(targets) != 272 or len(training) != 3347:
        raise ValueError("Approved train/validation eligibility count changed")
    saved = {row["id"]: row for row in demo["games"]}
    if set(saved) != {r["game_id"] for r in targets} or len(saved) != len(demo["games"]):
        raise ValueError("Historical saved-artifact population mismatch")
    predictions, discrepancies, max_error = [], [], 0.0
    for target in targets:
        reconstructed = reconstruct(rows, target, model)
        issues = compare_saved(reconstructed, saved[target["game_id"]])
        if issues:
            discrepancies.append({"id": target["game_id"], "issues": issues})
        max_error = max(max_error, abs(reconstructed["home_probability"] - saved[target["game_id"]]["home_probability"]))
        reconstructed["outcome_home"] = int(target["home_score"] > target["away_score"])
        predictions.append(reconstructed)
    if discrepancies:
        raise ValueError("Historical replay disagrees with preserved evidence: " + json.dumps(discrepancies))
    y, p = [g["outcome_home"] for g in predictions], [g["home_probability"] for g in predictions]
    results = {"incumbent": scores(y, p), "home_rate": scores(y, [home_rate]*len(y)), "coin": scores(y, [.5]*len(y))}
    calibration = reliability(y, p)
    uncertainty = block_intervals(y, p, home_rate, [(g["season"],g["week"]) for g in predictions])
    for kind, saved_id in (("incumbent", "schedule"), ("home_rate", "home"), ("coin", "coin")):
        original = next(m for m in demo["evaluation"]["models"] if m["id"] == saved_id)
        if any(abs(results[kind][key]-original[key]) > 1e-12 for key in results[kind]):
            raise ValueError("Reported validation metric did not reproduce")
    original_ci = demo["evaluation"]["brier_difference"]
    for key, saved_key in (("estimate", "mean"), ("low", "low"), ("high", "high")):
        if abs(uncertainty["intervals"]["brier_difference_home"][key]-original_ci[saved_key]) > 1e-12:
            raise ValueError("Original paired validation uncertainty did not reproduce")
    if len(calibration) != len(demo["evaluation"]["calibration"]):
        raise ValueError("Original calibration bin count differs")
    for actual, expected in zip(calibration, demo["evaluation"]["calibration"], strict=True):
        if any(abs(actual[key]-expected[key]) > 1e-12 for key in expected):
            raise ValueError("Original calibration did not reproduce")
    exposure = json.loads((ROOT / "docs/HOLDOUT_EXPOSURE.json").read_bytes())
    return {"schema_version": 1, "mode": "rc1-event-time-historical-replay", "model_id": model["id"],
            "historical_publication_availability_proven": False, "prospective": False,
            "evaluation_population": {"season": 2023, "status": "selection-exposed-retrospective-diagnostic", "games": len(predictions)},
            "metrics": results, "by_season": [{"season": 2023, **results["incumbent"]}], "calibration": calibration,
            "uncertainty": uncertainty, "predictions": predictions,
            "verification": {"all_saved_probabilities_and_factors_match": True, "discrepancies": discrepancies,
                             "largest_probability_error": max_error, "frozen_file_checks": checks,
                             "original_metrics_calibration_and_uncertainty_reproduced": True},
            "boundaries": {"fit_seasons": [2010,2022], "evaluated_seasons": [2023], "historical_training_count": len(training),
                           "source_seasons": [2010,2023], "source_count": len(rows),
                           "history_ties_count_half": True, "binary_targets_exclude_ties": True,
                           "fit_calls": 0, "network_calls": 0, "protected_seasons_consumed": [],
                           "holdout_status": exposure["status"], "public_writes": 0},
            "provenance": {"source": manifest, "source_sha256": SOURCE_SHA, "model_freeze_sha256": FREEZE_SHA,
                           "saved_demo_sha256": DEMO_SHA, "code_sha256": digest((ROOT / "ml/replay.py").read_bytes()),
                           "protocol_sha256": digest((ROOT / "docs/RC1_REPLAY_PROTOCOL.md").read_bytes()),
                           "training_home_rate": home_rate},
            "saved_challenger_checks": verify_saved_challenger(),
            "limitations": ["Corrected historical data lacks original publication-vintage proof; event-time eligibility is not proven historical information availability.",
                "2023 was used to select the incumbent; replay is a reused retrospective diagnostic, not prospective or untouched-test accuracy.",
                "Incumbent seasons2010–2022 are fitting data and are not reported as valid independent backtest seasons.",
                "One season and18week blocks limit intervals; repeated-team dependence across weeks and model selection are not fully captured.",
                "Calibration bins are descriptive; no calibration transform was fitted by this harness.",
                "Probabilities condition on non-ties. No2024–2025 data was consumed, and prior legacy aggregate exposure remains disclosed."]}


def write_evidence(result, generated_at):
    report = dict(result, generated_at=generated_at)
    body = canonical(report)
    directory = ROOT / "artifacts/rc1/replay"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / ("replay-" + digest(body) + ".json")
    if target.exists() and target.read_bytes() != body:
        raise ValueError("Replay evidence content-address collision")
    if not target.exists():
        target.write_bytes(body)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-repeat", action="store_true", help="Repeat all no-fit checks and compare deterministic payloads")
    args = parser.parse_args()
    result = replay()
    if args.verify_repeat and canonical(result) != canonical(replay()):
        raise AssertionError("Deterministic historical replay differs across identical runs")
    result["repeat_verified"] = args.verify_repeat
    result["deterministic_payload_sha256"] = digest(canonical(result))
    path = write_evidence(result, datetime.now(timezone.utc).isoformat())
    print(json.dumps({"evidence": str(path), "metrics": result["metrics"], "uncertainty": result["uncertainty"],
                      "repeat_verified": args.verify_repeat, "discrepancies": result["verification"]["discrepancies"]}, indent=2))


if __name__ == "__main__":
    main()
