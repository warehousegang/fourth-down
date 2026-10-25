"""Seven fixed, event-time V2 predictors, isolated from the incumbent pipeline."""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from ml.features import FEATURES as V1_FEATURES, Record, build_features as v1_features
from ml.v2_data import YEARS, team

FEATURES = [*V1_FEATURES, "prior_margin_diff", "adjusted_offense_ypp_diff", "adjusted_defense_ypp_diff"]
REFERENCE_YPP = 5.5
SHRINK_GAMES = 4


@dataclass
class State:
    record: Record = field(default_factory=Record)
    raw_offense: list = field(default_factory=list)
    raw_defense: list = field(default_factory=list)
    adjusted_offense: list = field(default_factory=list)
    adjusted_defense: list = field(default_factory=list)
    ids: list = field(default_factory=list)
    days: list = field(default_factory=list)
    efficiency_history: list = field(default_factory=list)
    missing_score: bool = False
    missing_efficiency: bool = False
    missing_adjustment: bool = False

    def rating(self, field):
        return sum(getattr(self, field)) / (len(self.raw_offense) + SHRINK_GAMES)


def validate_totals(totals, games):
    columns = {"season", "game_id", "team", "opponent", "valid", "reason",
               "yards", "plays", "allowed_yards", "allowed_plays"}
    if not columns <= set(totals) or not totals.season.isin(YEARS).all():
        raise ValueError("Missing efficiency fields or protected/unsupported season")
    data = totals.copy()
    data["team"], data["opponent"] = data.team.map(team), data.opponent.map(team)
    if data.duplicated(["game_id", "team"]).any() or not data.valid.isin([True, False]).all():
        raise ValueError("Duplicate efficiency identity or invalid availability flag")
    lookup = games.set_index("game_id")
    result = {}
    for row in data.to_dict("records"):
        if row["game_id"] not in lookup.index:
            raise ValueError("Efficiency game absent from authorized schedule")
        game = lookup.loc[row["game_id"]]
        if row["season"] != game.season or {row["team"], row["opponent"]} != {game.home_team, game.away_team}:
            raise ValueError("Efficiency identity mismatch")
        if row["valid"]:
            for key in ("yards", "plays", "allowed_yards", "allowed_plays"):
                value = float(row[key])
                if not np.isfinite(value) or ("plays" in key and (value < 1 or value % 1)):
                    raise ValueError("Invalid efficiency total")
                row[key] = value
            if abs(row["yards"]) > 100 * row["plays"] or abs(row["allowed_yards"]) > 100 * row["allowed_plays"]:
                raise ValueError("Implausible efficiency total")
        result[(row["game_id"], row["team"])] = row
    for (game_id, own), row in result.items():
        other = result.get((game_id, row["opponent"]))
        if row["valid"] and other and other["valid"]:
            if row["yards"] != other["allowed_yards"] or row["plays"] != other["allowed_plays"]:
                raise ValueError("Offense/defense totals disagree")
    return result


def build_features(games, totals):
    # Existing guard rejects forbidden seasons before any result is inspected.
    v1_features(games)
    data = games[games.game_type.eq("REG")].copy()
    data["home_team"], data["away_team"] = data.home_team.map(team), data.away_team.map(team)
    incumbent = v1_features(data).set_index("game_id")
    stats = validate_totals(totals, data)
    data["day"] = pd.to_datetime(data.gameday)
    data = data.sort_values(["season", "day", "game_id"])
    states, rows = defaultdict(State), []
    for (season, day), group in data.groupby(["season", "day"], sort=False):
        updates = []
        for game in group.itertuples():
            home, away = states[(season, game.home_team)], states[(season, game.away_team)]
            priors = [states[(season - 1, t)] for t in (game.home_team, game.away_team)]
            reasons = []
            if any(not p.record.games or p.missing_score for p in priors):
                reasons.append("missing previous-season score history")
            if home.missing_score or away.missing_score:
                reasons.append("missing preceding current-season result")
            if home.missing_efficiency or away.missing_efficiency:
                reasons.append("missing preceding current-season efficiency")
            if home.missing_adjustment or away.missing_adjustment:
                reasons.append("missing opponent pregame efficiency")
            complete = pd.notna(game.home_score) and pd.notna(game.away_score)
            row = {"game_id": game.game_id, "season": int(season), "week": int(game.week),
                   "gameday": day.strftime("%Y-%m-%d"), "home_team": game.home_team, "away_team": game.away_team,
                   "cutoff": datetime.combine(day.date(), datetime.min.time(), ZoneInfo("America/New_York")).isoformat(),
                   "eligible": not reasons, "unavailable_reasons": reasons, "complete": complete,
                   "is_tie": bool(complete and game.home_score == game.away_score),
                   "home_win": int(game.home_score > game.away_score) if complete else None,
                   "home_games": home.record.games, "away_games": away.record.games,
                   "history_ids": home.ids + away.ids, "history_dates": home.days + away.days,
                   "prior_history_ids": priors[0].ids + priors[1].ids,
                   "efficiency_history": home.efficiency_history + away.efficiency_history,
                   **{f: float(incumbent.loc[game.game_id, f]) for f in V1_FEATURES},
                   "prior_margin_diff": priors[0].record.values(day)["margin"] - priors[1].record.values(day)["margin"],
                   "adjusted_offense_ypp_diff": home.rating("adjusted_offense") - away.rating("adjusted_offense"),
                   "adjusted_defense_ypp_diff": home.rating("adjusted_defense") - away.rating("adjusted_defense")}
            rows.append(row)
            # Freeze BOTH opponents' earlier ratings before any game on this date updates state.
            for own, opponent, name, margin in ((home, away, game.home_team, game.home_score - game.away_score),
                                               (away, home, game.away_team, game.away_score - game.home_score)):
                updates.append((own, game, name, margin, complete, opponent.rating("raw_offense"),
                                opponent.rating("raw_defense"), opponent.missing_efficiency or opponent.missing_score,
                                list(opponent.ids), list(opponent.days)))
        for state, game, name, margin, complete, opp_off, opp_def, opp_missing, opp_ids, opp_days in updates:
            if not complete:
                state.missing_score = state.missing_efficiency = True
                continue
            state.record.games += 1
            state.record.wins += 1 if margin > 0 else .5 if margin == 0 else 0
            state.record.margins.append(float(margin))
            state.record.last = day
            state.ids.append(game.game_id)
            state.days.append(day.strftime("%Y-%m-%d"))
            own = stats.get((game.game_id, name))
            other_name = game.away_team if name == game.home_team else game.home_team
            other = stats.get((game.game_id, other_name))
            if not own or not other or not own["valid"] or not other["valid"]:
                state.missing_efficiency = True
                continue
            offense = own["yards"] / own["plays"] - REFERENCE_YPP
            defense = own["allowed_yards"] / own["allowed_plays"] - REFERENCE_YPP
            state.raw_offense.append(offense)
            state.raw_defense.append(defense)
            state.adjusted_offense.append(offense - opp_def)
            state.adjusted_defense.append(defense - opp_off)
            state.missing_adjustment |= opp_missing
            state.efficiency_history.append({"game_id": game.game_id, "team": name,
                "gameday": day.strftime("%Y-%m-%d"), "own_ypp": offense + REFERENCE_YPP,
                "allowed_ypp": defense + REFERENCE_YPP, "opponent_pregame_offense": opp_off,
                "opponent_pregame_defense": opp_def, "opponent_history_ids": opp_ids,
                "opponent_history_dates": opp_days, "opponent_available": not opp_missing})
    return pd.DataFrame(rows)
