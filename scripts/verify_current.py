"""Independent raw-CSV check of current forecasts; no training or historical loader."""
import csv
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
EASTERN = ZoneInfo("America/New_York")
parse = lambda value: datetime.fromisoformat(value.replace("Z", "+00:00"))
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
read = lambda path: json.loads(path.read_text())
pointer = read(ROOT / "web/public/data/current/latest.json")
assert pointer["season"] >= 2026
assert pointer["file"] == f"forecast-{pointer['season']}-{pointer['sha256']}.json"
path = ROOT / "web/public/data/current" / pointer["file"]
assert sha(path) == pointer["sha256"]
artifact = read(path)
season = artifact["season"]
assert season == pointer["season"]
raw = ROOT / f"data/current/{season}/raw-{artifact['source']['raw_sha256']}.csv"
assert sha(raw) == artifact["source"]["raw_sha256"]
with raw.open() as stream:
    rows = list(csv.DictReader(stream))
assert {r["season"] for r in rows} == {str(season)}
rows = [r for r in rows if r["season_type"] == "REG"]
assert len(rows) == 272
alias = lambda team: {"AZ": "ARI", "LAR": "LA"}.get(team, team)
def ident(row):
    return f"ngs-{season}-{row['game_key']}"
def day(row):
    return parse(row["game_time"]).astimezone(EASTERN).date() if row["game_time"] else None
model = read(ROOT / "docs/FROZEN_MODEL.json")["model"]
assert artifact["model"] == model
prob_errors, factor_errors = [], []
for target in artifact["games"]:
    if target["status"] != "available":
        assert target["home_probability"] is None and target["reason"]
        continue
    source = next(r for r in rows if ident(r) == target["id"])
    assert parse(source["game_time"]) == parse(target["kickoff"]) > parse(artifact["as_of"])
    assert source["phase"] in ("", "SCHEDULED", "PREGAME", "PRE_GAME")
    assert target["day"] == str(day(source))
    assert target["home"] == alias(source["home_team_abbr"])
    assert target["away"] == alias(source["visitor_team_abbr"])
    expected_cutoff = min(parse(artifact["as_of"]), datetime.combine(day(source), datetime.min.time(), EASTERN))
    assert parse(target["cutoff"]) == expected_cutoff
    values = {}
    for side in ("home", "away"):
        team = target[side]
        past = sorted([r for r in rows if day(r) and day(r) < day(source)
            and team in (alias(r["home_team_abbr"]), alias(r["visitor_team_abbr"]))], key=lambda r:(day(r), ident(r)))
        assert all(r["phase"] in ("FINAL", "FINAL OVERTIME") and r["validated"] == "true" for r in past)
        assert [h["id"] for h in target["history"][side]] == [ident(r) for r in past]
        assert all(parse(h["observed_at"]) < expected_cutoff for h in target["history"][side])
        margins = [(int(r["home_score"])-int(r["visitor_score"])) * (1 if alias(r["home_team_abbr"]) == team else -1) for r in past]
        n = len(past)
        wins = sum(1 if m > 0 else .5 if m == 0 else 0 for m in margins)
        values[side] = [(wins+2)/(n+4), sum(margins)/(n+4), sum(margins[-5:])/(min(n,5)+2), min(14,(day(source)-day(past[-1])).days) if n else 7]
    log_odds = model["intercept"]
    for i, key in enumerate(model["features"]):
        h, a = values["home"][i], values["away"][i]
        contribution = (h-a)*model["coefficients"][i]
        log_odds += contribution
        f = target["factors"][i]
        assert f["key"] == key
        for actual, expected in [(f["home"],h),(f["away"],a),(f["difference"],h-a),(f["contribution"],contribution),(target["features"][key],h-a)]:
            factor_errors.append(abs(actual-expected))
    p = 1/(1+math.exp(-log_odds))
    prob_errors.extend([abs(target["home_probability"]-p),abs(target["away_probability"]-(1-p))])
assert max(prob_errors, default=0) < 1e-12
assert max(factor_errors, default=0) < 1e-12
print(json.dumps({"forecast_sha256":pointer["sha256"],"raw_sha256":sha(raw),"season":season,"week":artifact["week"],
    "source_regular_season_games":len(rows),"available_forecasts":len(prob_errors)//2,"factors_checked":len(factor_errors)//5,
    "max_probability_error":max(prob_errors,default=0),"max_factor_error":max(factor_errors,default=0),
    "method":"Independent 2026 raw CSV queries and direct formulas; no production state/scoring functions, fitting, holdout reads or accuracy evaluation"},indent=2))
