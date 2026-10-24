"""Explicit season-isolated acquisition. Never use the all-season schedule loader."""
import csv
import hashlib
import io
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from ml.data import ROOT

EASTERN = ZoneInfo("America/New_York")
RELEASE = "https://api.github.com/repos/sportsdataverse/sportsdataverse-data/releases/tags/nfl_ngs_schedules"
DOWNLOAD = "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/nfl_ngs_schedules"
TEAMS = set("ARI ATL BAL BUF CAR CHI CIN CLE DAL DEN DET GB HOU IND JAX KC LA LAC LV MIA MIN NE NO NYG NYJ PHI PIT SEA SF TB TEN WAS".split())
ALIASES = {"AZ": "ARI", "LAR": "LA"}
FINAL = {"FINAL", "FINAL OVERTIME"}
SCHEDULED = {"", "SCHEDULED", "PREGAME", "PRE_GAME"}


def timestamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timestamps must carry a timezone")
    return result.astimezone(timezone.utc)


def iso(value):
    return value.astimezone(timezone.utc).isoformat()


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def current_season(now):
    local = now.astimezone(EASTERN)
    return local.year if local.month >= 3 else local.year - 1


def check_season(season):
    if type(season) is not int or season < 2026:
        raise ValueError("Protected/unsupported season; current adapter accepts 2026 onward only")


def normalize(raw, season, full_coverage=True):
    check_season(season)
    source = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    # Verify the season field on EVERY row before touching score fields.
    if not source or any(r.get("season") != str(season) for r in source):
        raise ValueError("Mixed, protected or missing source season")
    required = {"season_type", "week", "game_key", "game_id", "game_time", "game_date", "phase",
                "home_team_abbr", "visitor_team_abbr", "home_score", "visitor_score", "validated"}
    if not required <= set(source[0]):
        raise ValueError("Missing source columns")
    games = []
    for r in source:
        if r["season_type"] != "REG":
            continue
        home = ALIASES.get(r["home_team_abbr"], r["home_team_abbr"])
        away = ALIASES.get(r["visitor_team_abbr"], r["visitor_team_abbr"])
        if home not in TEAMS or away not in TEAMS or home == away or not r["game_key"].isdigit():
            raise ValueError("Invalid team or stable game key")
        week = int(r["week"])
        if not 1 <= week <= 18 or str(week) != r["week"]:
            raise ValueError("Invalid regular-season week")
        kickoff = timestamp(r["game_time"]) if r["game_time"] else None
        day = kickoff.astimezone(EASTERN).date() if kickoff else (
            datetime.strptime(r["game_date"], "%m/%d/%Y").date() if r["game_date"] else None)
        if day and not datetime(season, 8, 1).date() <= day <= datetime(season + 1, 2, 28).date():
            raise ValueError("Game date outside season")
        phase = r["phase"].upper().strip()
        if phase == "CANCELED":
            phase = "CANCELLED"
        scores = []
        for key in ("home_score", "visitor_score"):
            value = r[key]
            if value and (not value.isdigit() or not 0 <= int(value) <= 200):
                raise ValueError("Invalid score")
            scores.append(int(value) if value else None)
        games.append({"id": f"ngs-{season}-{r['game_key']}", "source_game_id": r["game_id"],
                      "season": season, "week": week, "home": home, "away": away,
                      "day": day.isoformat() if day else None, "kickoff": iso(kickoff) if kickoff else None,
                      "phase": phase, "home_score": scores[0], "away_score": scores[1],
                      "validated": r["validated"].lower() == "true",
                      "stadium": r.get("site_full_name") or "Venue unavailable"})
    if len({g["id"] for g in games}) != len(games):
        raise ValueError("Duplicate stable game IDs")
    if full_coverage:
        counts = Counter(t for g in games for t in (g["home"], g["away"]))
        if len(games) != 272 or set(counts) != TEAMS or set(counts.values()) != {17}:
            raise ValueError("Incomplete regular-season coverage; expected 272 games and 17 per team")
        if len({(g["week"], t) for g in games for t in (g["home"], g["away"])}) != 544:
            raise ValueError("Duplicate team/week schedule entries")
    return sorted(games, key=lambda g: g["id"])


def download(url, maximum=2_000_000):
    request = Request(url, headers={"User-Agent": "FourthDown-local-research/1.0", "Accept": "application/vnd.github+json"})
    with urlopen(request, timeout=30) as response:
        raw = response.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError("Source exceeds size limit")
    return raw


def acquire(season=None):
    now = datetime.now(timezone.utc)
    season = current_season(now) if season is None else season
    check_season(season)
    if season != current_season(now):
        raise ValueError("Acquisition is current-season only")
    release = json.loads(download(RELEASE))  # Metadata only; never fetch other season assets.
    name = f"ngs_schedule_{season}.csv"
    asset = next((a for a in release["assets"] if a["name"] == name), None)
    url = f"{DOWNLOAD}/{name}"
    if asset is None or asset["browser_download_url"] != url:
        raise ValueError("Current-season asset missing or unexpected URL")
    raw = download(url)
    if asset.get("digest") != "sha256:" + sha(raw):
        raise ValueError("Source changed during fetch or checksum missing; no snapshot promoted")
    games = normalize(raw, season)
    retrieved = datetime.now(timezone.utc)
    updated = timestamp(asset["updated_at"])
    if updated > retrieved:
        raise ValueError("Source timestamp is in the future")
    snapshot = {"schema_version": 1, "season": season, "retrieved_at": iso(retrieved),
                "source_updated_at": iso(updated), "source_url": url, "raw_sha256": sha(raw),
                "asset_id": asset["id"], "license_url": "https://github.com/sportsdataverse/sportsdataverse-data/blob/main/LICENSE",
                "source_name": "SportsDataverse / NFL Next Gen Stats schedules", "games": games}
    directory = ROOT / "data/current" / str(season)
    directory.mkdir(parents=True, exist_ok=True)
    raw_path = directory / f"raw-{sha(raw)}.csv"
    if not raw_path.exists():
        raw_path.write_bytes(raw)
    body = canonical(snapshot)
    path = directory / f"snapshot-{sha(body)}.json"
    if not path.exists():
        path.write_bytes(body)
    return path


def load_snapshot(path, season):
    check_season(season)
    path = Path(path).resolve()
    directory = (ROOT / "data/current" / str(season)).resolve()
    if path.parent != directory or not path.name.startswith("snapshot-"):
        raise ValueError("Only versioned snapshots in the allowed current-season directory may be read")
    body = path.read_bytes()
    if path.name != f"snapshot-{sha(body)}.json":
        raise ValueError("Snapshot checksum mismatch")
    snapshot = json.loads(body)
    if snapshot["season"] != season or any(g["season"] != season for g in snapshot["games"]):
        raise ValueError("Mixed or protected season in snapshot")
    raw = (directory / f"raw-{snapshot['raw_sha256']}.csv").read_bytes()
    if sha(raw) != snapshot["raw_sha256"] or normalize(raw, season) != snapshot["games"]:
        raise ValueError("Raw/normalized snapshot mismatch")
    return snapshot
