"""Offline prospective adapter preparation. No network, fitting or production writes.

Real 2025/2026 input loading is gated BEFORE any input file is opened. Synthetic
preparation receipts are explicitly non-prospective and cannot activate this gate.
"""
import argparse
import csv
import io
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from ml.current import frozen_model as frozen_v1
from ml.current_source import (DOWNLOAD, EASTERN, FINAL, SCHEDULED, TEAMS,
                               canonical, iso, normalize, sha, timestamp)
from ml.data import ROOT
from ml.features import Record
from ml.v2_data import COLUMNS, team
from ml.v2_features import FEATURES, REFERENCE_YPP, State

PLAN = ROOT / "research/v2/shadow/PLAN.json"
RESULT_SHA = "47ba6e069a6e3ddcc4a3181017a856fd7a866f9462598d20e6a7238299265c8a"
MODEL_SHA = "d4832bedb306ef315d179e5ec102e3048c2dbc7f584dd7c9803870af3b5438a6"
PBP_URL = "https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_2026.parquet"
PBP_LICENSE = "https://github.com/nflverse/nflverse-data/blob/main/LICENSE.md"
SCHEDULE_LICENSE = "https://github.com/sportsdataverse/sportsdataverse-data/blob/main/LICENSE"


def plan():
    return json.loads(PLAN.read_bytes())


def readiness():
    p = plan()
    return {"enabled": False, "status": "local-rehearsal-only" if p["prior_2025_use_approved"] else "preparation-only", "model_id": p["model_id"],
            "data_use_approved": p["prior_2025_use_approved"],
            "activation_approved": p["activation_approved"],
            "blockers": ([] if p["prior_2025_use_approved"] else ["2025 score-only prior use requires an explicit holdout amendment"]) +
                        ["Prospective activation and a future start timestamp require separate approval",
                         "Recurring capture and actual archived-V1 pairing remain disabled"]}


def require_activation():
    # This preparation has NO enable flag or unreviewed configuration bypass.
    # An approved activation revision must implement the signed-off boundary.
    raise PermissionError("V2 prospective execution disabled; recurring activation still awaits owner approval")


def frozen_v2():
    body = (ROOT / f"research/v2/result-{RESULT_SHA}.json").read_bytes()
    if sha(body) != RESULT_SHA:
        raise ValueError("Accepted V2 result changed")
    result = json.loads(body)
    model = result["model"]
    if (sha(canonical(model)) != MODEL_SHA or model["features"] != FEATURES
            or not model["preprocessing"]["absorbed_into_raw_coefficients"]):
        raise ValueError("Frozen V2 model/preprocessing mismatch")
    for name in ("ml/v2_features.py", "ml/v2_data.py"):
        if sha((ROOT / name).read_bytes()) != result["code_sha256"][name]:
            raise ValueError("Accepted V2 feature definitions changed")
    frozen_v1()  # Verify incumbent manifests without fitting or writing anything.
    return model


def probability(features):
    model = frozen_v2()
    if set(features) != set(FEATURES) or any(not math.isfinite(float(features[f])) for f in FEATURES):
        raise ValueError("Missing/nonfinite V2 input")
    # Exported raw-scale coefficients already contain StandardScaler; never scale twice.
    z = model["intercept"] + np.asarray([features[f] for f in FEATURES]) @ np.asarray(model["coefficients"])
    cal = model["calibration"]
    z = cal["intercept"] + cal["coefficient"] * z
    return float(1 / (1 + np.exp(-np.clip(z, -700, 700))))


def verify_capture(raw, receipt, kind, cutoff, *, simulation=False):
    """A checksum proves retained bytes, not the honesty of a supplied capture time."""
    if not simulation:
        require_activation()
    seasons = {"schedule": 2026, "pbp": 2026, "prior": 2025}
    season = seasons[kind]
    url = PBP_URL if kind == "pbp" else f"{DOWNLOAD}/ngs_schedule_{season}.csv"
    license_url = PBP_LICENSE if kind == "pbp" else SCHEDULE_LICENSE
    if (receipt.get("season") != season or receipt.get("kind") != kind
            or receipt.get("url") != url or receipt.get("license_url") != license_url
            or receipt.get("raw_sha256") != sha(raw)):
        raise ValueError("Capture scope, URL, license or checksum mismatch")
    if simulation and receipt.get("synthetic") is not True:
        raise ValueError("Preparation requires explicitly synthetic captures")
    retrieved, updated = timestamp(receipt["retrieved_at"]), timestamp(receipt["source_updated_at"])
    if not updated <= retrieved < cutoff:
        raise ValueError("Source must be observed strictly before the decision cutoff")
    if kind != "prior" and cutoff - retrieved > timedelta(hours=plan()["maximum_capture_age_hours"]):
        raise ValueError("Capture was not checked within the fixed six-hour window")
    return dict(receipt)


def _prior_scores(raw, *, full_coverage=True):
    """Score-only 2025 parser; caller must pass the real-data gate or synthetic proof."""
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    if not rows or any(r.get("season") != "2025" for r in rows):
        raise ValueError("Prior capture must contain only 2025, never 2024/mixed seasons")
    games = []
    for r in rows:
        if r["season_type"] != "REG":
            continue
        home, away = team(r["home_team_abbr"]), team(r["visitor_team_abbr"])
        if home not in TEAMS or away not in TEAMS or home == away or not r["game_key"].isdigit():
            raise ValueError("Invalid prior identity")
        if r["phase"].upper() not in FINAL or r["validated"].lower() != "true":
            raise ValueError("Previous season must be complete and verified")
        scores = [r["home_score"], r["visitor_score"]]
        if any(not s.isdigit() or not 0 <= int(s) <= 200 for s in scores):
            raise ValueError("Invalid previous-season score")
        kickoff = timestamp(r["game_time"])
        day = kickoff.astimezone(EASTERN).date()
        if not datetime(2025, 8, 1).date() <= day <= datetime(2026, 2, 28).date():
            raise ValueError("Prior game outside 2025 season")
        games.append(dict(id=f"ngs-2025-{r['game_key']}", season=2025, home=home, away=away,
                          home_score=int(scores[0]), away_score=int(scores[1]), day=day.isoformat(),
                          kickoff=iso(kickoff)))
    counts = Counter(t for g in games for t in (g["home"], g["away"]))
    if len({g["id"] for g in games}) != len(games):
        raise ValueError("Duplicate previous-season game")
    if full_coverage and (len(games) != 272 or set(counts) != TEAMS or set(counts.values()) != {17}):
        raise ValueError("Incomplete prior season; no neutral or substitute-year imputation")
    return games


def _pbp_totals(raw, games, target_day):
    parquet = pq.ParquetFile(io.BytesIO(raw))
    if parquet.metadata.num_rows > 100_000:
        raise ValueError("Unbounded PBP capture")
    if set(parquet.read(columns=["season"]).column("season").to_pylist()) != {2026}:
        raise ValueError("PBP must contain 2026 only; protected/mixed season rejected")
    columns = [*COLUMNS, "week", "home_team", "away_team", "game_date"]
    pbp = parquet.read(columns=columns).to_pandas()
    expected = {(g["week"], g["home"], g["away"], g["day"]): g for g in games
                if g["day"] and g["day"] < target_day}
    totals, joins = {}, []
    prior = pbp[pbp.season_type.eq("REG") & pbp.game_date.lt(target_day)]
    for pbp_id, frame in prior.groupby("game_id", sort=True):
        identities = frame[["week", "home_team", "away_team", "game_date"]].drop_duplicates()
        if len(identities) != 1 or frame.play_id.isna().any() or frame.play_id.duplicated().any():
            raise ValueError("Ambiguous PBP identity or duplicate plays")
        week, home, away, day = identities.iloc[0].tolist()
        game = expected.get((int(week), team(home), team(away), day))
        if game is None or pbp_id != f"2026_{int(week):02d}_{away}_{home}":
            raise ValueError("Unverified PBP/schedule join; reschedule requires review")
        plays = frame[frame.play_type.isin(["pass", "run"])].copy()
        flags = ["qb_kneel", "qb_spike", "two_point_attempt"]
        if any(not plays[f].isin([0, 1]).all() for f in flags):
            raise ValueError("Missing/invalid scrimmage flags")
        plays = plays[(plays[flags] == 0).all(axis=1)]
        plays["posteam"], plays["defteam"] = plays.posteam.map(team), plays.defteam.map(team)
        yards = pd.to_numeric(plays.yards_gained, errors="coerce")
        if (not np.isfinite(yards).all() or not yards.between(-100, 100).all()
                or not plays.posteam.isin([game["home"], game["away"]]).all()
                or not plays.defteam.isin([game["home"], game["away"]]).all()
                or plays.posteam.eq(plays.defteam).any()):
            raise ValueError("Invalid scrimmage yards/team")
        for own, other in ((game["home"], game["away"]), (game["away"], game["home"])):
            n, against = int(plays.posteam.eq(own).sum()), int(plays.posteam.eq(other).sum())
            if not n or not against:
                raise ValueError("Missing offensive/defensive plays")
            key = (game["id"], own)
            if key in totals:
                raise ValueError("Multiple PBP IDs map to one schedule game")
            totals[key] = dict(yards=float(yards[plays.posteam.eq(own)].sum()), plays=n,
                               allowed_yards=float(yards[plays.posteam.eq(other)].sum()), allowed_plays=against)
        joins.append(dict(game_id=game["id"], pbp_game_id=pbp_id, day=day))
    return totals, joins


def feature_state(target, games, totals, priors, cutoff):
    """Pure kernel. Event-time formulas equal accepted V2; observations must predate cutoff.

    Earlier opponent baselines are reconstructed from the captured vintage but
    never from opponents' later games. This is not vintage proof for older games.
    """
    if not target["kickoff"] or target["phase"] not in SCHEDULED:
        raise ValueError("Kickoff unconfirmed or game not scheduled")
    day = datetime.fromisoformat(target["day"]).date()
    states = defaultdict(State)
    prior_records, prior_ids = defaultdict(Record), defaultdict(list)
    if (len({g["id"] for g in games}) != len(games)
            or any(g["season"] != target["season"] for g in games)
            or any(g["season"] != target["season"] - 1 for g in priors)):
        raise ValueError("Duplicate/mixed-season state")
    for g in sorted(priors, key=lambda g: (g["day"], g["id"])):
        if timestamp(g["kickoff"]) >= cutoff:
            raise ValueError("Prior-season input occurs after cutoff")
        for own, margin in ((g["home"], g["home_score"] - g["away_score"]),
                            (g["away"], g["away_score"] - g["home_score"])):
            prior_records[own].games += 1
            prior_records[own].margins.append(float(margin))
            prior_ids[own].append(g["id"])
    earlier = [g for g in games if g["id"] != target["id"] and g["phase"] != "CANCELLED"
               and g["day"] and g["day"] < target["day"]]
    for g in games:
        if not g["day"] and g["week"] < target["week"] and g["phase"] != "CANCELLED":
            for name in (g["home"], g["away"]): states[name].missing_score = True
    grouped = defaultdict(list)
    for g in earlier: grouped[g["day"]].append(g)
    for played in sorted(grouped):
        updates = []
        for g in sorted(grouped[played], key=lambda g: g["id"]):
            good = (g["phase"] in FINAL and g["validated"] and g["kickoff"]
                    and timestamp(g["kickoff"]) < cutoff and timestamp(g["observed_at"]) < cutoff
                    and all(type(g[k]) is int and 0 <= g[k] <= 200 for k in ("home_score", "away_score")))
            for own, opponent in ((g["home"], g["away"]), (g["away"], g["home"])):
                other = states[opponent]
                updates.append((g, own, opponent, good, other.rating("raw_offense"),
                                other.rating("raw_defense"), other.missing_efficiency or other.missing_score,
                                list(other.ids), list(other.days)))
        for g, own, opponent, good, opp_off, opp_def, missing, ids, days in updates:
            state = states[own]
            if not good:
                state.missing_score = state.missing_efficiency = True
                continue
            margin = (g["home_score"] - g["away_score"]) * (1 if own == g["home"] else -1)
            state.record.games += 1
            state.record.wins += 1 if margin > 0 else .5 if margin == 0 else 0
            state.record.margins.append(float(margin))
            state.record.last = datetime.fromisoformat(played).date()
            state.ids.append(g["id"]); state.days.append(played)
            row, other = totals.get((g["id"], own)), totals.get((g["id"], opponent))
            if not row or not other:
                state.missing_efficiency = True
                continue
            for r in (row, other):
                if any(not math.isfinite(float(r[k])) for k in ("yards", "plays", "allowed_yards", "allowed_plays")) or min(r["plays"], r["allowed_plays"]) <= 0:
                    raise ValueError("Invalid required efficiency totals")
            if row["yards"] != other["allowed_yards"] or row["plays"] != other["allowed_plays"]:
                raise ValueError("Efficiency sides disagree")
            off, defense = row["yards"] / row["plays"] - REFERENCE_YPP, row["allowed_yards"] / row["allowed_plays"] - REFERENCE_YPP
            state.raw_offense.append(off); state.raw_defense.append(defense)
            state.adjusted_offense.append(off - opp_def); state.adjusted_defense.append(defense - opp_off)
            state.missing_adjustment |= missing
            state.efficiency_history.append(dict(game_id=g["id"], team=own, gameday=played,
                opponent_pregame_offense=opp_off, opponent_pregame_defense=opp_def,
                opponent_history_ids=ids, opponent_history_dates=days))
    features, history = {}, {}
    for side in ("home", "away"):
        name = target[side]; state = states[name]; prior = prior_records[name]
        if (not prior.games or state.missing_score or state.missing_efficiency or state.missing_adjustment):
            raise ValueError(f"Missing required {side} prior/current/opponent state")
        values = state.record.values(day)
        values.update(prior_margin=prior.values(day)["margin"],
                      adjusted_offense_ypp=state.rating("adjusted_offense"),
                      adjusted_defense_ypp=state.rating("adjusted_defense"))
        features[side] = values
        history[side] = dict(ids=state.ids, dates=state.days, prior_ids=prior_ids[name],
                             efficiency=state.efficiency_history)
    return {f: features["home"][f.removesuffix("_diff")] - features["away"][f.removesuffix("_diff")] for f in FEATURES}, history


def _produce(captures, game_id, generated_at=None, *, simulation=False):
    if not simulation:
        require_activation()
        if generated_at is not None:
            raise ValueError("Real forecasts must use the actual generation clock")
    generated = timestamp(generated_at) if simulation else datetime.now(timezone.utc)
    raw, schedule_receipt = captures["schedule"]
    if any(r.get("synthetic") is not simulation for _, r in captures.values()):
        raise ValueError("Synthetic and real capture modes cannot be mixed")
    games = normalize(raw, 2026, full_coverage=not simulation)
    if simulation and any(not g["source_game_id"].startswith("fixture-") for g in games):
        raise ValueError("Synthetic-only schedule identities required")
    if not simulation and any(g["source_game_id"].startswith("fixture-") for g in games):
        raise ValueError("Synthetic schedule cannot enter prospective records")
    target = next(g for g in games if g["id"] == game_id)
    if not target["kickoff"]:
        raise ValueError("Kickoff unconfirmed")
    kickoff = timestamp(target["kickoff"]); cutoff = kickoff - timedelta(minutes=60)
    if not cutoff <= generated < kickoff:
        raise ValueError("Generation must follow the decision cutoff and precede kickoff")
    if not simulation and (not plan()["activation_at"] or timestamp(plan()["activation_at"]) >= cutoff):
        raise ValueError("Cutoff must follow the approved prospective start")
    provenance = [verify_capture(*captures[k], k, cutoff, simulation=simulation) for k in ("schedule", "pbp", "prior")]
    for g in games: g["observed_at"] = schedule_receipt["retrieved_at"]
    priors = _prior_scores(captures["prior"][0], full_coverage=not simulation)
    totals, joins = _pbp_totals(captures["pbp"][0], games, target["day"])
    base = dict(schema_version=1, mode="v2-shadow-simulation" if simulation else "v2-shadow-forecast", prospective=not simulation,
                game_id=game_id, season=2026, week=target["week"], home=target["home"], away=target["away"],
                kickoff=target["kickoff"], cutoff=iso(cutoff), generated_at=iso(generated),
                model_id=frozen_v2()["id"], model_sha256=MODEL_SHA, result_sha256=RESULT_SHA,
                protocol_sha256=sha((PLAN.parent / "PROTOCOL.md").read_bytes()),
                configuration_sha256=sha(PLAN.read_bytes()), code_sha256=sha(Path(__file__).read_bytes()),
                sources=provenance, joins=joins, threshold=.5,
                feature_version="v2-efficiency-1", home_probability=None, away_probability=None,
                features={}, history={}, status="unavailable",
                limitations=["Synthetic software demonstration; excluded from all real scorecards" if simulation else "Private shadow estimate; not a V1 public forecast or promotion",
                             "No QB, injury, weather or news inputs", "Probabilities condition on non-ties",
                             "Opponent earlier-date states use the vintage captured before target cutoff"],
                source_age_hours={r["kind"]:(cutoff-timestamp(r["source_updated_at"])).total_seconds()/3600 for r in provenance})
    try:
        features, history = feature_state(target, games, totals, priors, cutoff)
    except ValueError as exc:
        return dict(base, unavailable_reason=str(exc))
    p = probability(features)
    return dict(base, status="available", unavailable_reason=None, features=features, history=history,
                home_probability=p, away_probability=1-p)


def simulate(captures, game_id, generated_at):
    """Exercise the full adapter on explicitly synthetic bytes; never a real forecast."""
    return _produce(captures, game_id, generated_at, simulation=True)


def run(input_manifest, game_id=None):
    # Deliberately do not open input_manifest while either decision is pending.
    require_activation()
    from ml.v2_shadow_store import existing, write
    manifest_path = Path(input_manifest)
    if manifest_path.is_symlink() or manifest_path.stat().st_size > 100_000:
        raise ValueError("Invalid shadow capture manifest")
    manifest = json.loads(manifest_path.read_bytes())
    if set(manifest) != {"schedule", "pbp", "prior"} or not game_id:
        raise ValueError("Exactly three scoped captures and a game ID are required")
    captures = {}
    for kind in ("schedule", "pbp", "prior"):
        item = manifest[kind]
        name = item["file"]
        if Path(name).name != name or name.startswith("."):
            raise ValueError("Capture paths must be filenames beside the manifest")
        path = manifest_path.parent / name
        limit = 128_000_000 if kind == "pbp" else 2_000_000
        if path.is_symlink() or not 0 < path.stat().st_size <= limit:
            raise ValueError("Invalid/bounded capture file required")
        captures[kind] = (path.read_bytes(), item["receipt"])
    # Retrying an already sealed decision returns its original time and probability.
    games = normalize(captures["schedule"][0], 2026)
    target = next(g for g in games if g["id"] == game_id)
    if not target["kickoff"]:
        raise ValueError("Kickoff unconfirmed")
    kickoff = timestamp(target["kickoff"])
    identity = dict(mode="v2-shadow-forecast", season=2026, game_id=game_id,
                    kickoff=target["kickoff"], cutoff=iso(kickoff - timedelta(minutes=60)))
    retained = existing(identity)
    return retained if retained else write(_produce(captures, game_id))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-manifest", type=Path)
    parser.add_argument("--game-id")
    args = parser.parse_args()
    if args.input_manifest:
        print(json.dumps(run(args.input_manifest, args.game_id), indent=2))
    else:
        print(json.dumps(readiness(), indent=2))


if __name__ == "__main__":
    main()
