
import nflreadpy as nfl
import numpy as np
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    log_loss,
)

# Load actual historical games
games = nfl.load_schedules(
    seasons=list(range(2010, 2026))
).to_pandas()

games = games[
    (games["game_type"] == "REG")
    & games["home_score"].notna()
    & games["away_score"].notna()
].copy()

# Exclude ties for this binary baseline
games = games[
    games["home_score"] != games["away_score"]
].copy()

games["home_win"] = (
    games["home_score"] > games["away_score"]
).astype(int)

# Chronological season split
train = games[games["season"] <= 2022]
validation = games[games["season"] == 2023]
test = games[games["season"].between(2024, 2025)]

# Estimate probability using TRAINING data only
home_win_rate = train["home_win"].mean()

# Constant probability forecast for every test game
probabilities = np.full(len(test), home_win_rate)

# Predict home team when training home-win rate > 50%
predictions = (probabilities >= 0.5).astype(int)

actual = test["home_win"]

print("Training games:", len(train))
print("Validation games:", len(validation))
print("Test games:", len(test))
print("Training home-win rate:", round(home_win_rate, 4))
print("Test accuracy:", round(accuracy_score(actual, predictions), 4))
print("Test Brier score:", round(brier_score_loss(actual, probabilities), 4))
print("Test log loss:", round(log_loss(actual, probabilities, labels=[0, 1]), 4))



# Compare against a 50/50 probability baseline
coin_flip_probs = np.full(len(test), 0.5)

print("\n--- Baseline Comparison ---")

print(
    "Coin flip Brier:",
    round(brier_score_loss(actual, coin_flip_probs), 4)
)

print(
    "Coin flip log loss:",
    round(log_loss(actual, coin_flip_probs, labels=[0, 1]), 4)
)

print(
    "Home advantage Brier:",
    round(brier_score_loss(actual, probabilities), 4)
)

print(
    "Home advantage log loss:",
    round(log_loss(actual, probabilities, labels=[0, 1]), 4)
)
