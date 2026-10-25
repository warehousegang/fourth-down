"""Predeclared local V2 experiment. Fitting authorized only for this research pipeline."""
import argparse
import importlib.metadata
import json
import platform
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from ml.challenger import (CONFIG as PRIOR_CONFIG, SOURCE_SHA, canonical, fit, frozen_model,
                           metrics, predict, sha)
from ml.data import ROOT, load_snapshot
from ml.features import FEATURES as V1_FEATURES, build_features as v1_features
from ml.v2_data import DIRECTORY, YEARS, load_inputs
from ml.v2_features import FEATURES, REFERENCE_YPP, SHRINK_GAMES, build_features

CONFIG = {"version": "v2-efficiency-1", "features": FEATURES, "seasons": list(YEARS),
          "training_start": 2011, "diagnostic_seasons": list(range(2018, 2024)),
          "estimator": PRIOR_CONFIG["estimator"], "calibration": PRIOR_CONFIG["calibration"],
          "primary": "calibrated_v2", "comparator": "calibrated_four_feature",
          "reference_ypp": REFERENCE_YPP, "shrink_games": SHRINK_GAMES,
          "seed": 42, "bootstrap_replicates": 2000, "threshold": .5, "locked_seasons": [2024, 2025]}


def verify_declaration():
    declaration = json.loads((DIRECTORY / "declaration.json").read_bytes())
    if declaration["config"] != CONFIG or declaration["protocol_sha256"] != sha((DIRECTORY / "EXPERIMENT.md").read_bytes()):
        raise ValueError("V2 pre-fit declaration changed")
    return declaration


def calibration(y, p):
    y, p = np.asarray(y, int), np.asarray(p, float)
    bins = np.minimum((p * 10).astype(int), 9)
    rows = []
    for index in range(10):
        selected = bins == index
        rows.append({"lower": index / 10, "upper": (index + 1) / 10, "count": int(selected.sum()),
                     "predicted": float(p[selected].mean()) if selected.any() else None,
                     "observed": float(y[selected].mean()) if selected.any() else None})
    return {"bins": rows, "ece": sum(r["count"] * abs(r["predicted"] - r["observed"]) for r in rows if r["count"]) / len(y)}


def report(rows, keys, comparator="four_feature"):
    rows = sorted(rows, key=lambda r: (r["season"], r["week"], r["game_id"]))
    y = np.asarray([r["home_win"] for r in rows], int)
    p = np.asarray([[r["probabilities"][k] for k in keys] for r in rows])
    clipped = np.clip(p, np.finfo(float).eps, 1 - np.finfo(float).eps)
    scores = np.stack([(p >= .5) == y[:, None], (p - y[:, None]) ** 2,
                       -(y[:, None] * np.log(clipped) + (1-y[:, None]) * np.log1p(-clipped))], axis=2)
    seasons, weeks = np.asarray([r["season"] for r in rows]), np.asarray([r["week"] for r in rows])
    # Sum within intact blocks; weighted sums equal concatenating every sampled game.
    groups = [[scores[(seasons == s) & (weeks == w)] for w in sorted(set(weeks[seasons == s]))]
              for s in sorted(set(seasons))]
    sums = [np.asarray([block.sum(axis=0) for block in group]) for group in groups]
    counts = [np.asarray([len(block) for block in group]) for group in groups]
    rng = np.random.default_rng(CONFIG["seed"])
    samples = []
    for _ in range(CONFIG["bootstrap_replicates"]):
        draws = [rng.integers(len(group), size=len(group)) for group in groups]
        numerator = sum(values[draw].sum(axis=0) for values, draw in zip(sums, draws, strict=True))
        denominator = sum(values[draw].sum() for values, draw in zip(counts, draws, strict=True))
        samples.append(numerator / denominator)
    samples = np.asarray(samples)
    names = ["accuracy", "brier", "log_loss"]
    summary = {key: {**metrics(y, p[:, i]), "calibration": calibration(y, p[:, i]),
                     "intervals": {name: np.quantile(samples[:, i, j], [.025, .975]).tolist() for j, name in enumerate(names)}}
               for i, key in enumerate(keys)}
    candidate, reference = keys.index("v2"), keys.index(comparator)
    paired = {name: {"mean": float(scores[:, candidate, j].mean() - scores[:, reference, j].mean()),
                     "low": float(np.quantile(samples[:, candidate, j] - samples[:, reference, j], .025)),
                     "high": float(np.quantile(samples[:, candidate, j] - samples[:, reference, j], .975))}
              for j, name in enumerate(names)}
    return {"models": summary, "v2_minus_comparator": paired, "comparator": comparator,
            "uncertainty": {"unit": "season-week", "stratified_by_season": True, "replicates": 2000, "seed": 42,
                            "blocks_per_season": {str(s): len(g) for s, g in zip(sorted(set(seasons)), groups, strict=True)}}}


def fit_fold(train, cal, columns):
    if (train.empty or cal.empty or not train.season.between(2011, 2021).all()
            or not cal.season.between(2017, 2022).all() or cal.season.nunique() != 1
            or train.season.min() != 2011 or train.season.max() != cal.season.min() - 1
            or set(train.season) != set(range(2011, int(cal.season.min())))
            or not set(columns) <= set(FEATURES)):
        raise ValueError("V2 fit violates declared chronological boundary")
    if not np.isfinite(train[columns].to_numpy(float)).all() or not np.isfinite(cal[columns].to_numpy(float)).all():
        raise ValueError("Unavailable training features")
    model = fit(train, cal, columns, calibrate=True)
    # Independent exported-scaler check covers every real fit, not just a mock.
    np.testing.assert_allclose(model["preprocessing"]["mean"], train[columns].mean().to_numpy(), atol=1e-12, rtol=0)
    expected_scale = train[columns].std(ddof=0).to_numpy(copy=True)
    expected_scale[expected_scale == 0] = 1
    np.testing.assert_allclose(model["preprocessing"]["scale"], expected_scale, atol=1e-12, rtol=0)
    return model


def experiment():
    declaration, incumbent = verify_declaration(), frozen_model()
    games, source = load_snapshot()
    if source["sha256"] != SOURCE_SHA:
        raise ValueError("Unapproved historical snapshot")
    totals, provenance = load_inputs()
    all_rows = build_features(games, totals)
    rows = all_rows[all_rows.season.ge(2011) & all_rows.eligible & all_rows.complete & ~all_rows.is_tie].copy()
    coverage = []
    for season, group in all_rows.groupby("season", sort=True):
        exclusions = [{"game_id": r.game_id, "reasons": r.unavailable_reasons +
                       (["warmup"] if season == 2010 else []) +
                       (["incomplete outcome"] if not r.complete else ["tie"] if r.is_tie else [])}
                      for r in group.itertuples() if season == 2010 or not r.eligible or not r.complete or r.is_tie]
        coverage.append({"season": int(season), "source_games": len(group),
                         "eligible_labeled": int((group.eligible & group.complete & ~group.is_tie & group.season.ge(2011)).sum()),
                         "exclusions": exclusions,
                         "reason_counts": dict(Counter(reason for r in exclusions for reason in r["reasons"]))})
    folds, predictions = [], []
    for season in CONFIG["diagnostic_seasons"]:
        train = rows[rows.season.between(2011, season-2)]
        cal, held = rows[rows.season.eq(season-1)], rows[rows.season.eq(season)]
        v2 = fit_fold(train, cal, FEATURES)
        baseline = fit_fold(train, cal, V1_FEATURES)
        probabilities = {"v2": predict(v2, held), "four_feature": predict(baseline, held),
                         "raw_v2": predict(v2, held, calibrated=False),
                         "raw_four_feature": predict(baseline, held, calibrated=False),
                         "home_rate": np.full(len(held), train.home_win.mean()), "coin": np.full(len(held), .5)}
        if season == 2023:
            probabilities["frozen_v1"] = predict(incumbent, held)
        fold_rows = []
        for i, row in enumerate(held.to_dict("records")):
            fold_rows.append({k: row[k] for k in ("game_id", "season", "week", "gameday", "cutoff", "home_win")})
            fold_rows[-1].update(features={f: row[f] for f in FEATURES},
                                 probabilities={key: float(p[i]) for key, p in probabilities.items()})
        predictions.extend(fold_rows)
        folds.append({"season": season, "train_n": len(train), "calibration_n": len(cal),
                      "train_seasons": [2011, season-2], "calibration_season": season-1,
                      "v2_model": v2, "four_feature_model": baseline,
                      "report": report(fold_rows, list(probabilities))})
    keys = ["v2", "four_feature", "raw_v2", "raw_four_feature", "home_rate", "coin"]
    pooled = report(predictions, keys)
    last = [r for r in predictions if r["season"] == 2023]
    separate = report(last, ["v2", "frozen_v1"], comparator="frozen_v1")
    frozen_rows = v1_features(games)
    frozen_rows = frozen_rows[frozen_rows.season.eq(2023) & frozen_rows.complete & ~frozen_rows.is_tie]
    separate["frozen_v1_full_2023"] = metrics(frozen_rows.home_win, predict(incumbent, frozen_rows))
    separate["interpretation"] = "Selection-exposed 2023; frozen V1 trained 2010–2022, unlike both controlled comparators"
    criteria = {"pooled_brier_improvement_at_least_0_002": pooled["v2_minus_comparator"]["brier"]["mean"] <= -.002,
                "paired_upper_bound_below_zero": pooled["v2_minus_comparator"]["brier"]["high"] < 0,
                "no_season_brier_regression_over_0_01": all(f["report"]["v2_minus_comparator"]["brier"]["mean"] <= .01 for f in folds),
                "pooled_ece_at_most_0_05": pooled["models"]["v2"]["calibration"]["ece"] <= .05,
                "every_season_ece_at_most_0_10": all(f["report"]["models"]["v2"]["calibration"]["ece"] <= .10 for f in folds)}
    model = dict(folds[-1]["v2_model"], feature_version=CONFIG["version"], threshold=.5,
                 protocol_sha256=declaration["protocol_sha256"], input_sha256=provenance["derived_sha256"])
    model["id"] = "v2-efficiency-" + sha(canonical(model))[:12]
    snapshots = all_rows[["game_id", "season", "week", "gameday", "cutoff", "eligible", "complete", "is_tie", "home_win", *FEATURES]].copy()
    feature_bytes = snapshots.to_csv(index=False, lineterminator="\n", float_format="%.17g").encode()
    result = {"schema_version": 1, "status": "research-only-not-promoted", "config": CONFIG, "declaration": declaration,
              "model": model, "source": provenance, "coverage": coverage, "folds": folds,
              "predictions": predictions, "pooled": pooled, "frozen_v1_2023": separate,
              "feature_snapshots_sha256": sha(feature_bytes),
              "criteria": criteria, "retrospective_criteria_passed": all(criteria.values()),
              "promotion_eligible": False, "shadow_2026_enabled": False,
              "blockers": ["2025 prior-season input is protected", "No prospective full-season shadow evaluation",
                           "Historical publication vintages unavailable", "No owner promotion approval"],
              "limitations": ["Corrected retrospective data, reused diagnostic seasons, selection-exposed 2023",
                              "Week-block intervals may miss cross-week team dependence",
                              "YPP ignores down, distance, situation, turnovers and roster availability",
                              "No QB, injury, weather or news predictor; non-tie probability only"],
              "environment": {"python": platform.python_version(),
                              "packages": {p: importlib.metadata.version(p) for p in ("numpy", "pandas", "scikit-learn", "pyarrow")}},
              "code_sha256": {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in sorted((ROOT / "ml").glob("v2_*.py"))}}
    return result, feature_bytes


def immutable(path, body):
    if path.exists():
        if path.read_bytes() != body:
            raise ValueError("Immutable V2 research artifact conflict")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive create: reruns never overwrite existing model/evaluation evidence.
        with path.open("xb") as handle:
            handle.write(body)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-repeat", action="store_true")
    args = parser.parse_args()
    started = datetime.now(timezone.utc).isoformat()
    result, feature_bytes = experiment()
    if args.verify_repeat:
        repeated, repeated_features = experiment()
        if canonical(result) != canonical(repeated) or feature_bytes != repeated_features:
            raise AssertionError("V2 rerun did not reproduce exactly")
    payload = canonical(result)
    digest = sha(payload)
    immutable(DIRECTORY / f"result-{digest}.json", payload)
    immutable(DIRECTORY / f"features-{sha(feature_bytes)}.csv", feature_bytes)
    receipt = {"model_id": result["model"]["id"], "result_file": f"result-{digest}.json", "sha256": digest,
               "feature_file": f"features-{sha(feature_bytes)}.csv", "feature_sha256": sha(feature_bytes),
               "started_at": started, "completed_at": datetime.now(timezone.utc).isoformat(),
               "repeat_verified": args.verify_repeat, "comparison": "Entire result payload and all feature snapshots; timestamps excluded"}
    immutable(DIRECTORY / f"receipt-{sha(canonical(receipt))}.json", canonical(receipt))
    print(json.dumps({"receipt": receipt, "pooled": result["pooled"], "criteria": result["criteria"]}, indent=2))


if __name__ == "__main__":
    main()
