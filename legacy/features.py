
from collections import defaultdict

import nflreadpy as nfl
import pandas as pd


def build_features(games):
    games = games.copy()

    # Regular-season games with final scores
    games = games[
        (games["game_type"] == "REG")
        & games["home_score"].notna()
        & games["away_score"].notna()
    ].copy()

    games["gameday"] = pd.to_datetime(games["gameday"])

    # Sort chronologically within each season
    games = games.sort_values(
        ["season", "gameday", "gametime", "game_id"]
    ).reset_index(drop=True)

    records = defaultdict(lambda: {"wins": 0, "games": 0})
    rows = []

    for (season, gameday, gametime), group in games.groupby(
        ["season", "gameday", "gametime"],
        sort=False,
        dropna=False,
    ):
        # Reset team records at the start of each season
        # (handled by including season in the dictionary key).

        pending_updates = []

        for _, game in group.iterrows():
            home = game["home_team"]
            away = game["away_team"]

            home_record = records[(season, home)]
            away_record = records[(season, away)]

            home_pct = (
                home_record["wins"] / home_record["games"]
                if home_record["games"] > 0 else 0.5
            )

            away_pct = (
                away_record["wins"] / away_record["games"]
                if away_record["games"] > 0 else 0.5
            )

            rows.append({
                "game_id": game["game_id"],
                "season": season,
                "week": game["week"],
                "home_team": home,
                "away_team": away,
                "home_win_pct": home_pct,
                "away_win_pct": away_pct,
                "win_pct_diff": home_pct - away_pct,
                "home_win": int(
                    game["home_score"] > game["away_score"]
                ),
                "is_tie": bool(
                    game["home_score"] == game["away_score"]
                ),
            })

            # Defer result updates until all games at this
            # timestamp have received pregame features.
            pending_updates.append((
                home, away,
                game["home_score"], game["away_score"]
            ))

        for home, away, home_score, away_score in pending_updates:
            records[(season, home)]["games"] += 1
            records[(season, away)]["games"] += 1

            if home_score > away_score:
                records[(season, home)]["wins"] += 1
            elif away_score > home_score:
                records[(season, away)]["wins"] += 1
            else:
                # Ties count as half a win for each team.
                records[(season, home)]["wins"] += 0.5
                records[(season, away)]["wins"] += 0.5

    result = pd.DataFrame(rows)

    # Binary classification target excludes tied games.
    return result[~result["is_tie"]].drop(
        columns="is_tie"
    ).reset_index(drop=True)


if __name__ == "__main__":
    games = nfl.load_schedules(
        seasons=list(range(2010, 2026))
    ).to_pandas()

    features = build_features(games)

    print("Games processed:", len(features))
    print("\nFirst 10 rows:")
    print(features.head(10).to_string(index=False))

    print("\nWeek 1 feature check:")
    week1 = features[features["week"] == 1]

    assert (week1["home_win_pct"] == 0.5).all()
    assert (week1["away_win_pct"] == 0.5).all()
    assert (week1["win_pct_diff"] == 0).all()

    print("PASS: All Week 1 features are neutral")

    print("\nMissing values:")
    print(
        features[
            ["home_win_pct", "away_win_pct", "win_pct_diff"]
        ].isna().sum()
    )
