
import nflreadpy as nfl

# Download historical NFL schedules and results
games = nfl.load_schedules(
    seasons=list(range(2010, 2026))
).to_pandas()

# Keep completed regular-season games
games = games[
    (games["game_type"] == "REG")
    & games["home_score"].notna()
    & games["away_score"].notna()
].copy()

# Create our prediction target
games["home_win"] = (
    games["home_score"] > games["away_score"]
).astype(int)

# Exclude tied games for binary classification
games = games[
    games["home_score"] != games["away_score"]
].copy()

print("Games:", len(games))
print("Seasons:", games["season"].nunique())
print("Home win rate:", round(games["home_win"].mean(), 3))

print(
    games[
        [
            "season", "week",
            "home_team", "away_team",
            "home_score", "away_score",
            "home_win"
        ]
    ].head(10).to_string(index=False)
)
