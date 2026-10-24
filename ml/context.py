"""Current, timestamped football annotations. These inputs never alter model probabilities."""
import argparse
import csv
import io
import json
import math
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pyarrow.compute as pc
import pyarrow.parquet as pq

from ml.data import ROOT
from ml.current_source import (ALIASES, FINAL, SCHEDULED, TEAMS, canonical, check_season,
                               current_season, iso, load_snapshot, sha, timestamp)

SOURCES = {"injuries": ("injuries", "injuries_{season}.csv"),
           "depth_charts": ("depth_charts", "depth_charts_{season}.parquet"),
           "stats_team": ("stats_team", "stats_team_week_{season}.csv")}
LIMIT = 5_000_000
LICENSE = "CC BY 4.0; nflverse repository declaration"
LICENSE_URL = "https://github.com/nflverse/nflverse-data/blob/main/LICENSE.md"


def download(url):
    request = urllib.request.Request(url, headers={"User-Agent": "FourthDown-local-context/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read(LIMIT + 1)
    if len(body) > LIMIT:
        raise ValueError("Current context source exceeds 5MB bound")
    return body


def acquire(season, directory=None):
    check_season(season)
    if season != current_season(datetime.now(timezone.utc)):
        raise ValueError("Context acquisition accepts the current NFL season only")
    directory = Path(directory or ROOT / "data/current-context" / str(season))
    directory.mkdir(parents=True, exist_ok=True)
    sources = []
    # Exactly one metadata request and one bounded asset download per source; no retry loop.
    for identity, (tag, pattern) in SOURCES.items():
        name = pattern.format(season=season)
        metadata_url = f"https://api.github.com/repos/nflverse/nflverse-data/releases/tags/{tag}"
        metadata = json.loads(download(metadata_url))
        matching = [a for a in metadata.get("assets", []) if a["name"] == name]
        if len(matching) != 1 or matching[0]["size"] > LIMIT:
            raise ValueError("Expected bounded current-season source is unavailable")
        asset = matching[0]
        expected_url = f"https://github.com/nflverse/nflverse-data/releases/download/{tag}/{name}"
        if asset["browser_download_url"] != expected_url:
            raise ValueError("Unexpected context asset URL")
        body = download(expected_url)
        digest = sha(body)
        if asset.get("digest") != "sha256:" + digest:
            raise ValueError("Context asset has no matching publisher SHA256")
        source = {"id": identity, "file": digest + "-" + name, "sha256": digest, "url": expected_url,
                  "source_updated_at": asset["updated_at"], "retrieved_at": iso(datetime.now(timezone.utc)),
                  "asset_id": asset["id"], "license": LICENSE, "license_url": LICENSE_URL}
        if timestamp(source["source_updated_at"]) > timestamp(source["retrieved_at"]):
            raise ValueError("Source update cannot occur after its observation")
        decode(body, source, season)  # validate season before persisting a trusted receipt
        target = directory / source["file"]
        if target.exists() and target.read_bytes() != body:
            raise ValueError("Context raw snapshot conflict")
        if not target.exists():
            target.write_bytes(body)
        sources.append(source)
    receipt = {"schema_version": 1, "season": season, "sources": sources}
    path = directory / ("receipt-" + sha(canonical(receipt)) + ".json")
    if path.exists() and path.read_bytes() != canonical(receipt):
        raise ValueError("Context receipt conflict")
    if not path.exists():
        path.write_bytes(canonical(receipt))
    return path


def team(value):
    value = ALIASES.get(value, value)
    if value not in TEAMS:
        raise ValueError("Unsupported team identity")
    return value


def decode(body, source, season):
    check_season(season)
    identity = source["id"]
    if identity not in SOURCES or len(body) > LIMIT or not re.fullmatch(r"[0-9a-f]{64}", source["sha256"]) or sha(body) != source["sha256"]:
        raise ValueError("Unverified bounded context source")
    tag, pattern = SOURCES[identity]
    if source["url"] != f"https://github.com/nflverse/nflverse-data/releases/download/{tag}/{pattern.format(season=season)}":
        raise ValueError("Context source is not the exact approved season asset")
    if identity == "depth_charts":
        parquet = pq.ParquetFile(io.BytesIO(body))
        if parquet.metadata.num_rows > 1_000_000 or sum(parquet.metadata.row_group(i).total_byte_size for i in range(parquet.num_row_groups)) > 128_000_000:
            raise ValueError("Depth chart decompression exceeds bound")
        # The source is timestamp-indexed rather than season-column indexed. Read only dates first.
        dates = parquet.read(columns=["dt"]).column("dt").to_pylist()
        if any(current_season(timestamp(value)) != season for value in dates):
            raise ValueError("Mixed/protected season in depth chart timestamps")
        table = parquet.read(columns=["dt", "team", "player_name", "gsis_id", "espn_id", "pos_abb", "pos_rank"])
        table = table.filter(pc.equal(table["pos_abb"], "QB"))
        rows = table.to_pylist()
        for row in rows:
            row["team"] = team(row["team"])
        return rows
    reader = csv.DictReader(io.StringIO(body.decode("utf-8-sig")))
    required = {"season", "week", "team", "season_type"}
    required |= ({"gsis_id", "full_name", "position", "report_status", "practice_status"} if identity == "injuries"
                 else {"game_id", "opponent_team", "completions", "attempts", "passing_yards", "carries", "rushing_yards"})
    if not required <= set(reader.fieldnames or []):
        raise ValueError("Required context source columns unavailable")
    rows = []
    for row in reader:
        # Validate season before parsing any football observation from this row.
        if row["season"] != str(season):
            raise ValueError("Mixed/protected season in current context")
        if len(rows) >= 100_000:
            raise ValueError("Context row bound exceeded")
        if row["season_type"] != "REG":
            continue
        if not re.fullmatch(r"(?:[1-9]|1[0-8])", row["week"]):
            raise ValueError("Invalid context week")
        row["week"] = int(row["week"])
        row["team"] = team(row["team"])
        if identity == "stats_team":
            row["opponent_team"] = team(row["opponent_team"])
            if not row["game_id"].startswith(str(season) + "_"):
                raise ValueError("Mixed/protected stats identity")
        rows.append(row)
    return rows


def load_receipt(path, season):
    check_season(season)
    path = Path(path)
    raw = path.read_bytes()
    if path.name != "receipt-" + sha(raw) + ".json":
        raise ValueError("Context receipt checksum mismatch")
    receipt = json.loads(raw)
    check_season(receipt["season"])
    if receipt["season"] != season or type(receipt["schema_version"]) is not int or receipt["schema_version"] != 1:
        raise ValueError("Unsupported or protected context receipt")
    if {s["id"] for s in receipt["sources"]} != set(SOURCES) or len(receipt["sources"]) != len(SOURCES):
        raise ValueError("Context receipt requires exactly three distinct sources")
    decoded = {}
    for source in receipt["sources"]:
        if not re.fullmatch(r"[0-9a-f]{64}", source["sha256"]):
            raise ValueError("Invalid context raw digest")
        if type(source["asset_id"]) is not int or source["asset_id"] <= 0:
            raise ValueError("Invalid source asset identity")
        if not timestamp(source["source_updated_at"]) <= timestamp(source["retrieved_at"]):
            raise ValueError("Invalid source timestamp ordering")
        expected = source["sha256"] + "-" + SOURCES[source["id"]][1].format(season=season)
        if source["file"] != expected:
            raise ValueError("Invalid context raw path")
        decoded[source["id"]] = decode((path.parent / source["file"]).read_bytes(), source, season)
    return receipt, decoded


def source_available(source, cutoff):
    updated, retrieved = timestamp(source["source_updated_at"]), timestamp(source["retrieved_at"])
    return updated <= retrieved < cutoff and cutoff - updated <= timedelta(hours=48)


def injuries_for(rows, source, target, club, cutoff):
    warning = "The source has no report publication timestamp. This is an observed weekly report, not proof of game-day availability. Missing reports do not mean healthy."
    result = {"status": "unavailable", "source_id": "injuries", "players": [], "report_published_at": None,
              "observed_at": source["retrieved_at"], "warnings": [warning]}
    if not source_available(source, cutoff):
        result["warnings"].append("Source was unavailable at this cutoff or its update is stale")
        return result
    selected = [row for row in rows if row["team"] == club and row["week"] == target["week"]]
    seen = set()
    for row in selected:
        identity = row["gsis_id"] or row["full_name"]
        if not identity or identity in seen:
            result["warnings"].append("Conflicting or duplicated player report; team report withheld")
            result["players"] = []
            return result
        seen.add(identity)
        result["players"].append({"player_id": row["gsis_id"] or None, "name": row["full_name"], "position": row["position"],
             "report_status": row["report_status"] or "Not supplied", "practice_status": row["practice_status"] or "Not supplied",
             "report_issue": row.get("report_primary_injury") or None, "practice_issue": row.get("practice_primary_injury") or None})
    if selected:
        result["status"] = "observed"
    else:
        result["warnings"].append("No current-week report found for this team")
    return result


def quarterback_for(rows, source, club, cutoff):
    result = {"status": "unavailable", "source_id": "depth_charts", "depth_chart": [], "confirmed_starter": None,
              "report_published_at": None, "source_recorded_at": None, "observed_at": source["retrieved_at"],
              "warnings": ["Depth-chart order is not confirmation of the starting quarterback. No individual performance or availability adjustment enters the model."]}
    if not source_available(source, cutoff):
        result["warnings"].append("Source unavailable at cutoff or update stale")
        return result
    selected = [r for r in rows if r["team"] == club and timestamp(r["dt"]) < cutoff]
    if not selected:
        return result
    latest = max(timestamp(r["dt"]) for r in selected)
    if cutoff - latest > timedelta(hours=48) or latest > timestamp(source["source_updated_at"]):
        result["warnings"].append("Timestamped depth chart is stale or future-dated")
        return result
    selected = [r for r in selected if timestamp(r["dt"]) == latest]
    result["source_recorded_at"] = iso(latest)
    seen = set()
    for row in sorted(selected, key=lambda r: (r["pos_rank"], r["player_name"])):
        identity = row["gsis_id"] or row["espn_id"]
        if not identity or identity in seen or type(row["pos_rank"]) is not int or row["pos_rank"] < 1:
            result["depth_chart"] = []
            result["warnings"].append("Conflicting or incomplete depth-chart identity")
            return result
        seen.add(identity)
        result["depth_chart"].append({"player_id": identity, "name": row["player_name"], "rank": row["pos_rank"]})
    result["status"] = "observed"
    return result


def totals(rows):
    result = {key: 0 for key in ("completions", "attempts", "passing_yards", "carries", "rushing_yards")}
    for row in rows:
        for key in result:
            value = float(row[key])
            if not math.isfinite(value) or value % 1 or not (-500 if "yards" in key else 0) <= value <= 2000:
                raise ValueError("Invalid observable team statistic")
            result[key] += int(value)
        if float(row["completions"]) > float(row["attempts"]):
            raise ValueError("Completions exceed attempts")
    return result


def ratios(values):
    return {"completion_rate": values["completions"] / values["attempts"] if values["attempts"] else None,
            "passing_yards_per_attempt": values["passing_yards"] / values["attempts"] if values["attempts"] else None,
            "rushing_yards_per_attempt": values["rushing_yards"] / values["carries"] if values["carries"] else None}


def performance_for(rows, source, schedule, target, club, cutoff):
    result = {"status": "unavailable", "source_id": "stats_team", "metrics": None, "totals": None,
              "completed_game_ids": [], "observed_at": source["retrieved_at"], "report_published_at": None,
              "warnings": ["Descriptive ratios from completed games only; not trained model inputs. EPA/CPOE are excluded because learned-model vintage is unverified."]}
    if not source_available(source, cutoff) or timestamp(schedule["retrieved_at"]) >= cutoff:
        result["warnings"].append("Stats or completed-result evidence unavailable before cutoff")
        return result
    games = [g for g in schedule["games"] if club in (g["home"], g["away"]) and g["id"] != target["id"]
             and g["phase"] in FINAL and g["validated"] is True and g["kickoff"] and g["day"] and target["day"]
             and g["day"] < target["day"] and timestamp(g["kickoff"]) < timestamp(schedule["retrieved_at"]) < cutoff
             and type(g["home_score"]) is int and type(g["away_score"]) is int]
    own, opponents = [], []
    try:
        for game in games:
            opposing = game["away"] if club == game["home"] else game["home"]
            identity = f"{game['season']}_{game['week']:02d}_{game['away']}_{game['home']}"
            matched = [r for r in rows if r["game_id"] == identity and r["week"] == game["week"]]
            home = [r for r in matched if r["team"] == club and r["opponent_team"] == opposing]
            away = [r for r in matched if r["team"] == opposing and r["opponent_team"] == club]
            if len(home) != 1 or len(away) != 1:
                raise ValueError("Completed-game stats missing, duplicated or ambiguous")
            own.append(home[0]); opponents.append(away[0])
        if not games:
            raise ValueError("No earlier completed games with verified stats")
        own_totals, opposing_totals = totals(own), totals(opponents)
        result.update(status="observed", metrics={"offense": ratios(own_totals), "opponent_allowed": ratios(opposing_totals)},
                      totals={"offense": own_totals, "opponent_allowed": opposing_totals}, completed_game_ids=sorted(g["id"] for g in games))
    except (KeyError, TypeError, ValueError) as error:
        result["warnings"].append(str(error))
    return result


def generate(schedule, receipt, decoded, as_of, generated_at):
    season = schedule["season"]
    check_season(season)
    cutoff, generated = timestamp(as_of), timestamp(generated_at)
    if receipt["season"] != season or current_season(cutoff) != season or generated < cutoff:
        raise ValueError("Context season or timestamp ordering mismatch")
    sources = {s["id"]: s for s in receipt["sources"]}
    if set(sources) != set(SOURCES):
        raise ValueError("Context requires three verified sources")
    for source in sources.values():
        if not timestamp(source["source_updated_at"]) <= timestamp(source["retrieved_at"]) < cutoff:
            raise ValueError("Context source was not available before cutoff")
    if not timestamp(schedule["source_updated_at"]) <= timestamp(schedule["retrieved_at"]) < cutoff:
        raise ValueError("Schedule was unavailable before context cutoff")
    if any(type(g["season"]) is not int or g["season"] != season or not g["id"].startswith(f"ngs-{season}-") for g in schedule["games"]):
        raise ValueError("Mixed/protected season in context schedule")
    if len({g["id"] for g in schedule["games"]}) != len(schedule["games"]):
        raise ValueError("Duplicate context schedule identity")
    upcoming = [g for g in schedule["games"] if g["phase"] in SCHEDULED and g["kickoff"] and timestamp(g["kickoff"]) > generated]
    week = min(upcoming, key=lambda g: timestamp(g["kickoff"]))["week"] if upcoming else None
    selected = sorted([g for g in upcoming if g["week"] == week], key=lambda g: (g["kickoff"],g["id"]))
    games = []
    for target in selected:
        sides = {}
        for side in ("home", "away"):
            club = target[side]
            sides[side] = {"team": club, "injuries": injuries_for(decoded["injuries"], sources["injuries"], target, club, cutoff),
                           "quarterback": quarterback_for(decoded["depth_charts"], sources["depth_charts"], club, cutoff),
                           "performance": performance_for(decoded["stats_team"], sources["stats_team"], schedule, target, club, cutoff)}
        games.append({"id": target["id"], "home": target["home"], "away": target["away"], "week": target["week"],
                      "kickoff": target["kickoff"], "cutoff": iso(cutoff), "teams": sides})
    valid_until = min([generated + timedelta(hours=24)] + [timestamp(s["source_updated_at"]) + timedelta(hours=48) for s in sources.values()])
    return {"schema_version": 1, "mode": "current-context", "season": season, "week": week,
            "generated_at": iso(generated), "as_of": iso(cutoff), "valid_until": iso(valid_until), "affects_probability": False,
            "sources": list(sources.values()), "games": games,
            "schedule_source": {k: schedule[k] for k in ("retrieved_at", "source_updated_at", "source_url", "raw_sha256")},
            "receipt_sha256": sha(canonical(receipt)), "pipeline_sha256": sha((ROOT / "ml/context.py").read_bytes()),
            "attribution": {"name": "nflverse", "url": "https://github.com/nflverse/nflverse-data", "license": "CC BY 4.0",
                            "license_url": "https://creativecommons.org/licenses/by/4.0/", "modifications": "Selected current-season rows; joined schedule identities; derived aggregate ratios; timestamped annotations"},
            "limitations": ["Current observed context only. No annotation changes the frozen model's features, coefficients or probabilities.",
                "Context cutoff is independently shown and may be later than the forecast's original input cutoff; these are not retroactive forecast inputs.",
                "The injury file supplies no report publication time. A weekly report observed now cannot establish prior availability or prove completeness.",
                "Depth-chart position does not confirm a starter. Its source_recorded_at is the provider snapshot timestamp, not proof of an original team publication. Individual quarterback performance is not ingested.",
                "Team statistics are observable aggregate ratios; EPA and CPOE are excluded. No efficiency predictive contribution has been trained or measured.",
                "No weather, verified news, travel-distance or protected2024–2025 input is acquired.",
                "nflverse repository CC BY4.0 terms and attribution are preserved; upstream public redistribution review remains a release gate."]}


def publish(artifact, directory=None):
    directory = Path(directory or ROOT / "web/public/data/context")
    directory.mkdir(parents=True, exist_ok=True)
    body = canonical(artifact); digest = sha(body); name = "context-" + digest + ".json"
    target = directory / name
    if target.exists() and target.read_bytes() != body:
        raise ValueError("Context immutable artifact conflict")
    if not target.exists():
        target.write_bytes(body)
    pointer = {"schema_version": 1, "file": name, "sha256": digest, "season": artifact["season"], "generated_at": artifact["generated_at"]}
    temporary = directory / ".latest.tmp"
    temporary.write_bytes(canonical(pointer)); temporary.replace(directory / "latest.json")
    return target


def refresh_context(schedule, receipt_path=None, as_of=None, generated_at=None):
    path = receipt_path or acquire(schedule["season"])
    receipt, decoded = load_receipt(path, schedule["season"])
    cutoff = as_of or iso(datetime.now(timezone.utc))
    generated = generated_at or iso(datetime.now(timezone.utc))
    return publish(generate(schedule, receipt, decoded, cutoff, generated))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, help="Verified current-season schedule snapshot")
    parser.add_argument("--season", required=True, type=int)
    parser.add_argument("--receipt", help="Replay a verified existing context receipt without network")
    parser.add_argument("--as-of"); parser.add_argument("--generated-at")
    args = parser.parse_args()
    check_season(args.season)
    snapshot = load_snapshot(args.snapshot, args.season)
    path = refresh_context(snapshot, args.receipt, args.as_of, args.generated_at)
    print(json.dumps({"artifact": str(path), "games": len(json.loads(path.read_bytes())["games"]), "affects_probability": False}))


if __name__ == "__main__":
    main()
