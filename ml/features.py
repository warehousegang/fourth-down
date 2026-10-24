"""Calendar-day batched, season-reset features. No results from cutoff day."""
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

VERSION = "daily-schedule-v1"
FEATURES = ["smooth_win_diff", "margin_diff", "recent_margin_diff", "rest_diff"]
LABELS = {"smooth_win_diff": "Season win rate", "margin_diff": "Season scoring margin",
          "recent_margin_diff": "Recent scoring margin", "rest_diff": "Rest days",
          "win_pct_diff": "Season win rate (original)"}


@dataclass
class Record:
    wins: float = 0
    games: int = 0
    margins: list = field(default_factory=list)
    last: object = None

    def values(self, day):
        return {"smooth_win": (self.wins + 2) / (self.games + 4),
                "margin": sum(self.margins) / (self.games + 4),
                "recent_margin": sum(self.margins[-5:]) / (min(5, self.games) + 2),
                "rest": min(14, (day - self.last).days) if self.last is not None else 7,
                "win_pct": self.wins / self.games if self.games else .5,
                "games": self.games}


def build_features(games):
    required = {"game_id", "season", "week", "game_type", "gameday", "gametime",
                "home_team", "away_team", "home_score", "away_score"}
    if not required <= set(games):
        raise ValueError(f"Missing source columns: {sorted(required - set(games))}")
    data = games.copy()
    if not data.season.between(2010, 2023).all():
        raise ValueError("Protected or unsupported season: only 2010–2023 is authorized.")
    if not data.season.mod(1).eq(0).all() or not (data.week.between(1, 18) & data.week.mod(1).eq(0)).all():
        raise ValueError("Season and week must be supported integers.")
    data = data[data.game_type.eq("REG")].copy()
    if data.game_id.isna().any() or data.game_id.duplicated().any():
        raise ValueError("Missing or duplicate game IDs.")
    if data[["season", "week", "home_team", "away_team", "gameday"]].isna().any().any():
        raise ValueError("Missing identity/date metadata.")
    if data.home_team.eq(data.away_team).any():
        raise ValueError("A team cannot play itself.")
    data["day"] = pd.to_datetime(data.gameday, errors="raise")
    for col in ["home_score", "away_score"]:
        values = pd.to_numeric(data[col], errors="raise")
        if ((values.dropna() < 0) | ~np.isfinite(values.dropna()) | (values.dropna() % 1 != 0)).any():
            raise ValueError("Invalid score.")
        data[col] = values
    data = data.sort_values(["season", "day", "game_id"])
    records = defaultdict(Record)
    rows = []
    for (season, day), group in data.groupby(["season", "day"], sort=False):
        updates = []
        # All rows on this day read the same earlier-day state.
        for game in group.itertuples():
            home, away = records[(season, game.home_team)], records[(season, game.away_team)]
            h, a = home.values(day), away.values(day)
            complete = pd.notna(game.home_score) and pd.notna(game.away_score)
            row = {"game_id": game.game_id, "season": int(season), "week": int(game.week),
                   "home_team": game.home_team, "away_team": game.away_team,
                   "gameday": day.strftime("%Y-%m-%d"),
                   "home_win": int(game.home_score > game.away_score) if complete else np.nan,
                   "is_tie": bool(complete and game.home_score == game.away_score),
                   "complete": complete}
            for key in h:
                row[f"home_{key}"] = h[key]
                row[f"away_{key}"] = a[key]
            for feature in FEATURES + ["win_pct_diff"]:
                name = feature.removesuffix("_diff")
                row[feature] = h[name] - a[name]
            rows.append(row)
            if complete:
                updates.append((home, away, game.home_score, game.away_score))
        for home, away, hs, aws in updates:
            for record, margin in [(home, hs - aws), (away, aws - hs)]:
                record.wins += 1 if margin > 0 else .5 if margin == 0 else 0
                record.games += 1
                record.margins.append(float(margin))
                record.last = day
    return pd.DataFrame(rows)
