"""Validation-only experiments. This module never accepts a holdout option."""
import hashlib
import json
from datetime import datetime, timezone

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from legacy.features import build_features as original_features
from ml.data import ROOT, load_snapshot
from ml.features import FEATURES, VERSION, build_features

SEED = 42
NAMES = {"coin": "50/50 baseline", "home": "Historical home advantage",
         "original": "Original logistic regression", "schedule": "Schedule logistic regression"}


def metrics(y, p):
    return {"n": len(y), "accuracy": float(accuracy_score(y, np.asarray(p) >= .5)),
            "brier": float(brier_score_loss(y, p)), "log_loss": float(log_loss(y, p, labels=[0, 1]))}


def fit_model(kind, train, columns=None):
    if kind in ("coin", "home"):
        p = .5 if kind == "coin" else float(train.home_win.mean())
        return {"kind": kind, "features": [], "intercept": float(np.log(p / (1 - p))), "coefficients": []}
    cols = columns if columns is not None else (["win_pct_diff"] if kind == "original" else FEATURES)
    estimator = LogisticRegression(max_iter=1000, random_state=SEED)
    # Preserve the original estimator and raw feature; scale only the new candidate.
    fitted = estimator if kind == "original" else make_pipeline(StandardScaler(), estimator)
    fitted.fit(train[cols], train.home_win.astype(int))
    coef, intercept = estimator.coef_[0], estimator.intercept_[0]
    if kind != "original":
        scaler = fitted.steps[0][1]
        coef = coef / scaler.scale_
        intercept -= float(np.dot(coef, scaler.mean_))
    model = {"kind": kind, "features": list(cols), "intercept": float(intercept), "coefficients": coef.tolist()}
    np.testing.assert_allclose(predict(model, train), fitted.predict_proba(train[cols])[:, 1], atol=1e-12)
    return model


def predict(model, frame):
    z = np.full(len(frame), model["intercept"])
    for col, coefficient in zip(model["features"], model["coefficients"], strict=True):
        z += frame[col].to_numpy(dtype=float) * coefficient
    return 1 / (1 + np.exp(-z))


def calibration(y, p):
    bins = np.minimum((np.asarray(p) * 10).astype(int), 9)
    return [{"bin": i, "count": int((bins == i).sum()),
             "predicted": float(np.asarray(p)[bins == i].mean()),
             "observed": float(np.asarray(y)[bins == i].mean())}
            for i in range(10) if (bins == i).any()]


def weekly_interval(y, p, baseline, weeks):
    difference = (np.asarray(p) - np.asarray(y)) ** 2 - (np.asarray(baseline) - np.asarray(y)) ** 2
    groups = [difference[np.asarray(weeks) == week] for week in sorted(set(weeks))]
    rng = np.random.default_rng(SEED)
    estimates = [np.concatenate([groups[i] for i in rng.integers(len(groups), size=len(groups))]).mean()
                 for _ in range(2000)]
    return {"mean": float(difference.mean()), "low": float(np.quantile(estimates, .025)),
            "high": float(np.quantile(estimates, .975)), "unit": "week", "replicates": 2000}


def train():
    games, manifest = load_snapshot()
    all_features = build_features(games)
    data = all_features[all_features.complete & ~all_features.is_tie].copy()
    original = original_features(games).set_index("game_id")
    # Independent implementation parity, not merely our own expected constants.
    np.testing.assert_allclose(data.win_pct_diff, original.loc[data.game_id, "win_pct_diff"], atol=0)
    training, validation = data[data.season <= 2022], data[data.season == 2023]
    if training.empty or validation.empty:
        raise ValueError("Training and validation must both contain labeled observations.")
    models = {kind: fit_model(kind, training) for kind in NAMES}
    probabilities = {kind: predict(model, validation) for kind, model in models.items()}
    results = [{"id": kind, "name": name, **metrics(validation.home_win, probabilities[kind])}
               for kind, name in NAMES.items()]
    minimum = min(row["brier"] for row in results)
    # Complexity-ordered, predeclared tolerance avoids promoting a negligible gain.
    selected = next(row["id"] for row in results if row["brier"] <= minimum + .001)
    model = models[selected]
    model.update({"name": NAMES[selected], "feature_version": VERSION,
                  "source_sha256": manifest["sha256"], "train_seasons": [2010, 2022], "seed": SEED})
    model["id"] = selected + "-v1-" + hashlib.sha256(json.dumps(model, sort_keys=True).encode()).hexdigest()[:10]
    ablations = []
    for removed in FEATURES:
        ablated = fit_model("schedule", training, [f for f in FEATURES if f != removed])
        ablations.append({"removed": removed, **metrics(validation.home_win, predict(ablated, validation))})
    backtests = []
    for season in range(2018, 2023):
        prior, held = data[data.season < season], data[data.season == season]
        current = fit_model(selected, prior)
        baseline = fit_model("home", prior)
        backtests.append({"season": season, "train_n": len(prior),
                          "model": metrics(held.home_win, predict(current, held)),
                          "baseline": metrics(held.home_win, predict(baseline, held))})
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "source": manifest,
              "feature_version": VERSION, "train_n": len(training), "validation_n": len(validation),
              "train_seasons": [2010, 2022], "validation_season": 2023,
              "home_win_rate": float(training.home_win.mean()), "selected": selected,
              "models": results, "ablations": ablations, "backtests": backtests,
              "calibration": calibration(validation.home_win, probabilities[selected]),
              "brier_difference": weekly_interval(validation.home_win, probabilities[selected],
                                                  probabilities["home"], validation.week),
              "holdout_status": "locked", "original_feature_parity": True,
              "selection_rule": "Simplest model within 0.001 Brier of validation best; fixed C=1; no search."}
    output = ROOT / "artifacts"
    output.mkdir(exist_ok=True)
    for name, value in [("model", model), ("evaluation", report)]:
        (output / f"{name}.json").write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"models": results, "selected": selected, "train_n": len(training),
                      "validation_n": len(validation), "brier_difference": report["brier_difference"]}, indent=2))


if __name__ == "__main__":
    train()
