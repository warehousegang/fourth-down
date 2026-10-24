
import nflreadpy as nfl
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    log_loss,
)

from features import build_features


# 1. Load historical games
games = nfl.load_schedules(
    seasons=list(range(2010, 2026))
).to_pandas()

# 2. Generate leakage-aware pregame features
data = build_features(games)

# 3. Preserve chronological season splits
train = data[data["season"] <= 2022]
validation = data[data["season"] == 2023]
test = data[data["season"].between(2024, 2025)]

# 4. Select our first feature and target
features = ["win_pct_diff"]

X_train = train[features]
y_train = train["home_win"]

X_validation = validation[features]
y_validation = validation["home_win"]

# 5. Train logistic regression
model = LogisticRegression(max_iter=1000)
model.fit(X_train, y_train)

# 6. Predict probabilities on validation data
probabilities = model.predict_proba(
    X_validation
)[:, 1]

predictions = (probabilities >= 0.5).astype(int)

# 7. Evaluate
print("Training games:", len(train))
print("Validation games:", len(validation))

print("\nLearned coefficients:")
print("Intercept:", round(model.intercept_[0], 4))
print("Win pct coefficient:", round(model.coef_[0][0], 4))

print("\n2023 Validation Results:")
print(
    "Accuracy:",
    round(accuracy_score(y_validation, predictions), 4)
)
print(
    "Brier score:",
    round(brier_score_loss(y_validation, probabilities), 4)
)
print(
    "Log loss:",
    round(log_loss(y_validation, probabilities), 4)
)


import numpy as np

# Baseline probability learned from training data only
baseline_probability = y_train.mean()

baseline_probs = np.full(
    len(y_validation),
    baseline_probability
)

baseline_predictions = (
    baseline_probs >= 0.5
).astype(int)

print("\n--- 2023 Validation Comparison ---")

print(f"{'Metric':<15} {'Baseline':>12} {'Logistic':>12}")

print(
    f"{'Accuracy':<15}"
    f"{accuracy_score(y_validation, baseline_predictions):>12.4f}"
    f"{accuracy_score(y_validation, predictions):>12.4f}"
)

print(
    f"{'Brier':<15}"
    f"{brier_score_loss(y_validation, baseline_probs):>12.4f}"
    f"{brier_score_loss(y_validation, probabilities):>12.4f}"
)

print(
    f"{'Log loss':<15}"
    f"{log_loss(y_validation, baseline_probs, labels=[0, 1]):>12.4f}"
    f"{log_loss(y_validation, probabilities, labels=[0, 1]):>12.4f}"
)


import pandas as pd

analysis = validation[
    [
        "game_id",
        "home_team",
        "away_team",
        "win_pct_diff",
        "home_win"
    ]
].copy()

analysis["baseline_prob"] = baseline_probs
analysis["logistic_prob"] = probabilities

analysis["baseline_pick"] = baseline_predictions
analysis["logistic_pick"] = predictions

disagreements = analysis[
    analysis["baseline_pick"] != analysis["logistic_pick"]
].copy()

disagreements["logistic_correct"] = (
    disagreements["logistic_pick"]
    == disagreements["home_win"]
)

print("\n--- Model Disagreements ---")
print("Total disagreements:", len(disagreements))

if len(disagreements) > 0:
    print(
        "Logistic correct on disagreements:",
        disagreements["logistic_correct"].sum()
    )

    print(
        disagreements[
            [
                "game_id",
                "win_pct_diff",
                "logistic_prob",
                "home_win",
                "logistic_correct"
            ]
        ].head(15).to_string(index=False)
    )
