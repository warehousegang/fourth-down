"""Bounded schedule-intelligence research; never fits or replaces the frozen incumbent."""
import argparse
import hashlib
import importlib.metadata
import json
import platform
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss
from sklearn.preprocessing import StandardScaler

from ml.data import ROOT, load_snapshot
from ml.features import Record, FEATURES as INCUMBENT_FEATURES, build_features as incumbent_features

VERSION = "schedule-intelligence-v1"
GROUPS = {"prior_strength": ["prior_smooth_win_diff", "prior_margin_diff"],
          "current_performance": ["smooth_win_diff"],
          "opponent_adjusted": ["opponent_adjusted_margin_diff"],
          "recent_trends": ["recent_margin_diff"],
          "home_road": ["venue_margin_diff", "neutral_site"],
          "scoring_margins": ["margin_diff"], "rest_travel": ["rest_diff", "bye_diff"]}
FEATURES = list(INCUMBENT_FEATURES) + ["prior_smooth_win_diff", "prior_margin_diff",
            "opponent_adjusted_margin_diff", "venue_margin_diff", "bye_diff", "neutral_site"]
CONFIG = {"version": VERSION, "features": FEATURES, "domain_groups": GROUPS, "seed": 42,
          "estimator": {"C": 1.0, "solver": "lbfgs", "max_iter": 2000, "random_state": 42},
          "calibration": {"C": 1000000.0, "solver": "lbfgs", "max_iter": 2000, "random_state": 42},
          "fold_seasons": list(range(2018, 2024)), "training_start": 2011,
          "classification_threshold": .5, "bootstrap_replicates": 2000,
          "locked_seasons": [2024, 2025]}
FROZEN_SHA = "2896a526ed8035b1674a6beb3c8d27c76ba4b3f466309bfeb729c6ddbf80f957"
SOURCE_SHA = "20f573837dac7d9ea41dade07b165de6164b3370d60e49d5242e5255cabb7d01"
ALIASES = {"STL": "LA", "SD": "LAC", "OAK": "LV"}


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def frozen_model():
    path = ROOT / "docs/FROZEN_MODEL.json"
    if sha(path.read_bytes()) != FROZEN_SHA:
        raise ValueError("Frozen manifest changed")
    freeze = json.loads(path.read_bytes())
    for name, checksum in freeze["file_sha256"].items():
        if sha((ROOT / name).read_bytes()) != checksum:
            raise ValueError("Frozen source changed: " + name)
    return freeze["model"]


@dataclass
class State:
    record: Record = field(default_factory=Record)
    opponent_adjusted: list = field(default_factory=list)
    home_margins: list = field(default_factory=list)
    road_margins: list = field(default_factory=list)
    history_ids: list = field(default_factory=list)
    history_dates: list = field(default_factory=list)
    missing: bool = False
    adjusted_missing: bool = False
    venue_missing: bool = False


def build_features(games):
    # Reuse validation and exact incumbent formulas without changing their protected guard.
    checked = incumbent_features(games)
    data = games.loc[games.game_type.eq("REG")].copy()
    data["day"] = pd.to_datetime(data.gameday)
    data = data.sort_values(["season", "day", "game_id"])
    states, rows = defaultdict(State), []
    for (season, day), group in data.groupby(["season", "day"], sort=False):
        updates = []
        for game in group.itertuples():
            home, away = ALIASES.get(game.home_team, game.home_team), ALIASES.get(game.away_team, game.away_team)
            hs, aws = states[(season, home)], states[(season, away)]
            hp, ap = states[(season - 1, home)], states[(season - 1, away)]
            h, a = hs.record.values(day), aws.record.values(day)
            h.update(prior_smooth_win=hp.record.values(day)["smooth_win"], prior_margin=hp.record.values(day)["margin"],
                     opponent_adjusted_margin=sum(hs.opponent_adjusted) / (hs.record.games + 4),
                     venue_margin=sum(hs.home_margins) / (len(hs.home_margins) + 4),
                     bye=int(hs.record.last is not None and (day - hs.record.last).days >= 12))
            a.update(prior_smooth_win=ap.record.values(day)["smooth_win"], prior_margin=ap.record.values(day)["margin"],
                     opponent_adjusted_margin=sum(aws.opponent_adjusted) / (aws.record.games + 4),
                     venue_margin=sum(aws.road_margins) / (len(aws.road_margins) + 4),
                     bye=int(aws.record.last is not None and (day - aws.record.last).days >= 12))
            complete = pd.notna(game.home_score) and pd.notna(game.away_score)
            reasons = []
            if not hp.record.games or not ap.record.games:
                reasons.append("prior-season history unavailable")
            if hs.missing or aws.missing or hp.missing or ap.missing or hs.adjusted_missing or aws.adjusted_missing:
                reasons.append("preceding result missing")
            venue_known = getattr(game, "location", None) in ("Home", "Neutral")
            if not venue_known or hs.venue_missing or aws.venue_missing:
                reasons.append("venue-role metadata unavailable")
            neutral = getattr(game, "location", None) == "Neutral"
            row = {"game_id": game.game_id, "season": int(season), "week": int(game.week),
                   "gameday": day.strftime("%Y-%m-%d"), "home_team": home, "away_team": away,
                   "complete": complete, "is_tie": bool(complete and game.home_score == game.away_score),
                   "home_win": int(game.home_score > game.away_score) if complete else None,
                   "eligible": not reasons, "unavailable_reasons": reasons, "neutral_site": float(neutral),
                   "history_ids": hs.history_ids + aws.history_ids,
                   "history_dates": hs.history_dates + aws.history_dates,
                   "prior_history_ids": hp.history_ids + ap.history_ids,
                   "home_games": h["games"], "away_games": a["games"]}
            for feature in FEATURES:
                if feature != "neutral_site":
                    key = feature.removesuffix("_diff")
                    row[feature] = h[key] - a[key]
            rows.append(row)
            updates.append((hs, aws, game, h["margin"], a["margin"], complete, neutral, venue_known, hs.missing, aws.missing))
        for hs, aws, game, hm, am, complete, neutral, venue_known, hm_missing, am_missing in updates:
            if not complete:
                hs.missing = aws.missing = True
                continue
            for state, margin, opponent_margin, role, opponent_missing in [(hs, game.home_score - game.away_score, am, "home", am_missing),
                                                         (aws, game.away_score - game.home_score, hm, "road", hm_missing)]:
                record = state.record
                record.games += 1
                record.wins += 1 if margin > 0 else .5 if margin == 0 else 0
                record.margins.append(float(margin))
                record.last = day
                state.opponent_adjusted.append(float(margin + opponent_margin))
                state.adjusted_missing = state.adjusted_missing or opponent_missing
                state.venue_missing = state.venue_missing or not venue_known
                if venue_known and not neutral:
                    getattr(state, role + "_margins").append(float(margin))
                state.history_ids.append(game.game_id)
                state.history_dates.append(day.strftime("%Y-%m-%d"))
    result = pd.DataFrame(rows)
    # Within-season franchise aliases never change incumbent values.
    reference = checked.set_index("game_id").loc[result.game_id]
    np.testing.assert_allclose(result[INCUMBENT_FEATURES], reference[INCUMBENT_FEATURES], atol=0)
    return result


def metrics(y, p):
    y, p = np.asarray(y, int), np.asarray(p, float)
    return {"n": len(y), "accuracy": float(accuracy_score(y, p >= .5)),
            "brier": float(brier_score_loss(y, p)), "log_loss": float(log_loss(y, p, labels=[0, 1]))}


def calibration_bins(y, p):
    y, p = np.asarray(y, int), np.asarray(p, float)
    indices = np.minimum((p * 10).astype(int), 9)
    return [{"bin": i, "count": int((indices == i).sum()),
             "predicted": float(p[indices == i].mean()), "observed": float(y[indices == i].mean())}
            for i in range(10) if (indices == i).any()]


def ece(y, p):
    return sum(row["count"] * abs(row["predicted"] - row["observed"]) for row in calibration_bins(y, p)) / len(y)


def logit(model, frame):
    return model["intercept"] + frame[model["features"]].to_numpy(float) @ np.asarray(model["coefficients"])


def predict(model, frame, calibrated=True):
    z = logit(model, frame)
    if calibrated and model.get("calibration"):
        z = model["calibration"]["intercept"] + model["calibration"]["coefficient"] * z
    return 1 / (1 + np.exp(-np.clip(z, -700, 700)))


def fit(train, cal, columns, calibrate=True):
    if not (train.season.max() < cal.season.min() and set(train.season).isdisjoint({2024, 2025})
            and set(cal.season).isdisjoint({2024, 2025})):
        raise ValueError("Training/calibration split violates temporal boundary")
    scaler = StandardScaler().fit(train[columns])
    estimator = LogisticRegression(**CONFIG["estimator"]).fit(scaler.transform(train[columns]), train.home_win.astype(int))
    raw_coefficients = estimator.coef_[0] / scaler.scale_
    model = {"features": list(columns), "intercept": float(estimator.intercept_[0] - raw_coefficients @ scaler.mean_),
             "coefficients": raw_coefficients.tolist(),
             "preprocessing": {"kind": "StandardScaler", "mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist(),
                               "absorbed_into_raw_coefficients": True},
             "fit_seasons": [int(train.season.min()), int(train.season.max())], "fit_n": len(train),
             "calibration": None}
    np.testing.assert_allclose(predict(model, train), estimator.predict_proba(scaler.transform(train[columns]))[:, 1], atol=1e-12)
    if calibrate:
        calibration = LogisticRegression(**CONFIG["calibration"]).fit(logit(model, cal).reshape(-1, 1), cal.home_win.astype(int))
        model["calibration"] = {"method": "Platt", "coefficient": float(calibration.coef_[0, 0]),
                                "intercept": float(calibration.intercept_[0]), "season": int(cal.season.min()), "n": len(cal)}
        np.testing.assert_allclose(predict(model, cal), calibration.predict_proba(logit(model, cal).reshape(-1, 1))[:, 1], atol=1e-12)
    return model


def interval(y, p, comparator, seasons, weeks):
    difference = (np.asarray(p) - np.asarray(y)) ** 2 - (np.asarray(comparator) - np.asarray(y)) ** 2
    seasons, weeks = np.asarray(seasons), np.asarray(weeks)
    groups = [[difference[(seasons == season) & (weeks == week)] for week in sorted(set(weeks[seasons == season]))]
              for season in sorted(set(seasons))]
    rng = np.random.default_rng(42)
    estimates = []
    for _ in range(CONFIG["bootstrap_replicates"]):
        sample = [group[i] for group in groups for i in rng.integers(len(group), size=len(group))]
        estimates.append(np.concatenate(sample).mean())
    return {"mean": float(difference.mean()), "low": float(np.quantile(estimates, .025)),
            "high": float(np.quantile(estimates, .975)), "unit": "season-week", "stratified_by_season": True,
            "replicates": CONFIG["bootstrap_replicates"], "seed": 42}


def verify_declaration():
    declaration = json.loads((ROOT / "docs/CHALLENGER_DECLARATION.json").read_text())
    if declaration["config"] != CONFIG or declaration["protocol_sha256"] != sha((ROOT / "docs/CHALLENGER_PROTOCOL.md").read_bytes()):
        raise ValueError("Predeclared protocol/configuration changed")
    return declaration


def experiment():
    declaration, incumbent = verify_declaration(), frozen_model()
    games, source = load_snapshot()
    if source["sha256"] != SOURCE_SHA:
        raise ValueError("Challenger only accepts the declared local snapshot")
    all_rows = build_features(games)
    rows = all_rows[all_rows.eligible & all_rows.complete & ~all_rows.is_tie & all_rows.season.ge(2011)].copy()
    folds, fold_predictions, ablation_rows, models = [], [], defaultdict(list), {}
    for season in CONFIG["fold_seasons"]:
        train = rows[rows.season.between(2011, season - 2)]
        cal, held = rows[rows.season.eq(season - 1)], rows[rows.season.eq(season)]
        model = fit(train, cal, FEATURES)
        recipe = fit(train, cal, INCUMBENT_FEATURES, calibrate=False)
        models[season] = model
        probabilities = {"challenger": predict(model, held), "raw_challenger": predict(model, held, calibrated=False),
                         "incumbent_recipe": predict(recipe, held), "home": np.full(len(held), train.home_win.mean()),
                         "coin": np.full(len(held), .5)}
        if season == 2023:
            probabilities["frozen_incumbent"] = predict(incumbent, held)
        record = {"season": season, "fit_seasons": model["fit_seasons"], "fit_n": len(train),
                  "calibration_season": season - 1, "calibration_n": len(cal),
                  "metrics": {kind: metrics(held.home_win, p) for kind, p in probabilities.items()},
                  "challenger_ece": ece(held.home_win, probabilities["challenger"]),
                  "calibration": calibration_bins(held.home_win, probabilities["challenger"])}
        folds.append(record)
        for i, row in enumerate(held.itertuples()):
            fold_predictions.append({"id": row.game_id, "season": season, "week": row.week, "gameday": row.gameday,
                                     "home_win": int(row.home_win), "features": {key: float(getattr(row, key)) for key in FEATURES},
                                     "probabilities": {key: float(p[i]) for key, p in probabilities.items()}})
        for domain, removed in GROUPS.items():
            ablated = fit(train, cal, [key for key in FEATURES if key not in removed])
            p = predict(ablated, held)
            ablation_rows[domain].append({"season": season, "removed": removed, "metrics": metrics(held.home_win, p),
                                         "probabilities": p.tolist()})
    final = models[2023]
    final.update({"name": "Schedule intelligence research challenger", "feature_version": VERSION,
                  "source_sha256": SOURCE_SHA, "threshold": .5, "seed": 42})
    final["id"] = "challenger-v1-" + sha(canonical(final))[:12]
    y = [row["home_win"] for row in fold_predictions]
    p = [row["probabilities"]["challenger"] for row in fold_predictions]
    recipe_p = [row["probabilities"]["incumbent_recipe"] for row in fold_predictions]
    seasons = [row["season"] for row in fold_predictions]
    weeks = [row["week"] for row in fold_predictions]
    pooled = {key: metrics(y, [row["probabilities"][key] for row in fold_predictions])
              for key in ("challenger", "raw_challenger", "incumbent_recipe", "home", "coin")}
    ablations = []
    for domain, results in ablation_rows.items():
        ablated_p = [probability for result in results for probability in result["probabilities"]]
        ablations.append({"domain": domain, "removed": GROUPS[domain], "ablated": metrics(y, ablated_p),
                          "full_minus_ablated_brier": pooled["challenger"]["brier"] - metrics(y, ablated_p)["brier"],
                          "uncertainty": interval(y, p, ablated_p, seasons, weeks),
                          "per_season": [{key: value for key, value in result.items() if key != "probabilities"} for result in results]})
    uncertainty = interval(y, p, recipe_p, seasons, weeks)
    diagnostic = folds[-1]["metrics"]
    latest = [row for row in fold_predictions if row["season"] == 2023]
    diagnostic_ci = interval([r["home_win"] for r in latest], [r["probabilities"]["challenger"] for r in latest],
                             [r["probabilities"]["frozen_incumbent"] for r in latest],
                             [r["season"] for r in latest], [r["week"] for r in latest])
    criteria = {"pooled_brier_improvement_at_least_0_002": uncertainty["mean"] <= -.002,
                "paired_brier_upper_bound_below_zero": uncertainty["high"] < 0,
                "no_season_regression_above_0_01": all(f["metrics"]["challenger"]["brier"] - f["metrics"]["incumbent_recipe"]["brier"] <= .01 for f in folds),
                "pooled_ece_at_most_0_05": ece(y, p) <= .05,
                "every_season_ece_at_most_0_10": all(f["challenger_ece"] <= .10 for f in folds),
                "prospective_full_season": False, "live_all_features_available": False, "owner_approved": False}
    inventory = json.loads((ROOT / "docs/INTELLIGENCE_DOMAINS.json").read_text())
    for domain in inventory["domains"]:
        evidence = next((a for a in ablations if a["domain"] == domain["id"]), None)
        domain["contribution"] = None if evidence is None else {"method": "fixed-config leave-domain-out, six chronological folds",
                    "full_minus_ablated_brier": evidence["full_minus_ablated_brier"], "uncertainty": evidence["uncertainty"],
                    "n": pooled["challenger"]["n"], "not_causal": True}
    return {"schema_version": 1, "mode": "challenger-research", "status": "research-only-not-promoted",
            "model": final, "incumbent_model_id": incumbent["id"], "config": CONFIG,
            "provenance": {"source": source, "source_sha256": SOURCE_SHA, "declaration": declaration,
                           "protocol_sha256": declaration["protocol_sha256"], "frozen_manifest_sha256": FROZEN_SHA,
                           "code_sha256": {name: sha((ROOT / name).read_bytes()) for name in ("ml/challenger.py", "ml/intelligence.py")},
                           "python": platform.python_version(),
                           "packages": {name: importlib.metadata.version(name) for name in ("numpy", "pandas", "scikit-learn")},
                           "dataset_counts": {"source": len(games), "eligible_labeled_2011_2023": len(rows),
                                               "missing_feature_rows": int((~all_rows.eligible & all_rows.season.ge(2011)).sum())}},
            "evaluation": {"diagnostic_season": 2023, "diagnostic_status": "selection-exposed-retrospective",
                           "challenger": diagnostic["challenger"], "incumbent": diagnostic["frozen_incumbent"],
                           "home": diagnostic["home"], "coin": diagnostic["coin"], "raw_challenger": diagnostic["raw_challenger"],
                           "incumbent_recipe": diagnostic["incumbent_recipe"], "backtests": folds, "pooled": pooled,
                           "calibration": folds[-1]["calibration"], "pooled_calibration": calibration_bins(y, p),
                           "pooled_ece": ece(y, p), "domain_ablations": ablations,
                           "uncertainty": {"pooled_vs_recipe": uncertainty, "diagnostic_vs_frozen_incumbent": diagnostic_ci}},
            "fold_models": [{"season": season, "model": model} for season, model in models.items()],
            "predictions": fold_predictions, "domains": inventory["domains"],
            "limitations": ["Research only; the frozen incumbent remains the operational model.",
                "All 2018–2023 results are retrospective; 2023 was already used in incumbent selection.",
                "Historical source is corrected and lacks archived publication-vintage snapshots.",
                "2024–2025 holdout remains locked and partially exposed by the previously disclosed baseline aggregates.",
                "No efficiency, quarterback, injury, weather, travel-distance or news input is trained.",
                "Prior-2025 strength for 2026 is protected; this challenger cannot issue current forecasts.",
                "Ablations are conditional correlated-feature comparisons, not causal evidence.",
                "Probabilities are conditional on non-ties; season-week uncertainty may miss cross-week team dependence."],
            "promotion": {"eligible": False, "approval_required": True, "criteria": criteria,
                          "blockers": [*(["At least one retrospective season exceeds the predeclared 0.10 ECE limit"] if not criteria["every_season_ece_at_most_0_10"] else []), "No prospective full-season shadow evidence", "2026 prior-season inputs unavailable under holdout restriction",
                                       "Historical publication vintages unavailable", "Owner promotion approval not granted"]},
            "attribution": {"name": "nflverse / Lee Sharpe", "url": "https://github.com/nflverse/nflverse-data",
                            "license": "CC BY 4.0", "license_url": "https://creativecommons.org/licenses/by/4.0/"}}


def publish(result, generated_at):
    result = dict(result, generated_at=generated_at)
    content = canonical(result)
    digest = sha(content)
    output = ROOT / "web/public/data/research"
    output.mkdir(parents=True, exist_ok=True)
    name = "challenger-" + digest + ".json"
    path = output / name
    if path.exists() and path.read_bytes() != content:
        raise ValueError("Immutable challenger artifact conflict")
    if not path.exists():
        path.write_bytes(content)
    pointer = {"schema_version": 1, "file": name, "sha256": digest, "model_id": result["model"]["id"], "generated_at": generated_at}
    temporary = output / "latest.json.tmp"
    temporary.write_bytes(canonical(pointer))
    temporary.replace(output / "latest.json")
    registry = {"schema_version": 1, "operational_model_id": result["incumbent_model_id"], "promotion_approval": None,
                "frozen_manifest_sha256": FROZEN_SHA, "models": [
                    {"id": result["incumbent_model_id"], "role": "frozen-incumbent", "artifact": "web/public/data/demo.json",
                     "sha256": sha((ROOT / "web/public/data/demo.json").read_bytes()), "immutable": True},
                    {"id": result["model"]["id"], "role": "research-challenger", "operational_status": "ineligible",
                     "artifact": "web/public/data/research/" + name, "sha256": digest, "promotion": result["promotion"]}],
                "rollback": {"strategy": "Explicit owner-approved registry revert to previously approved model and SHA; preserve forecast ledger",
                             "target_model_id": result["incumbent_model_id"], "automatic_promotion": False},
                "protocol": "docs/CHALLENGER_PROTOCOL.md"}
    (ROOT / "docs/MODEL_REGISTRY.json").write_text(json.dumps(registry, indent=2) + "\n")
    return pointer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-repeat", action="store_true")
    args = parser.parse_args()
    generated_at = datetime.now(timezone.utc).isoformat()
    result = experiment()
    repeated = None
    if args.verify_repeat:
        repeated = experiment()
        if canonical(result) != canonical(repeated):
            raise AssertionError("Fixed-config experiment was not exactly repeatable")
    result["reproducibility"] = {"repeat_verified": repeated is not None, "deterministic_payload_sha256": sha(canonical(result)),
                                 "comparison_excludes": ["generated_at", "reproducibility"]}
    pointer = publish(result, generated_at)
    print(json.dumps({"artifact": pointer, "diagnostic": result["evaluation"]["challenger"],
                      "pooled": result["evaluation"]["pooled"], "promotion": result["promotion"],
                      "repeat_verified": repeated is not None}, indent=2))


if __name__ == "__main__":
    main()
