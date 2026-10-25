"""Explicit, season-isolated research acquisition. Never downloads schedules or holdout."""
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from ml.challenger import SOURCE_SHA, canonical, sha
from ml.data import ROOT, load_snapshot

YEARS = tuple(range(2010, 2024))
ALIASES = {"STL": "LA", "SD": "LAC", "OAK": "LV", "LAR": "LA", "AZ": "ARI"}
COLUMNS = ["season", "season_type", "game_id", "play_id", "posteam", "defteam",
           "play_type", "yards_gained", "qb_kneel", "qb_spike", "two_point_attempt"]
DIRECTORY = ROOT / "research/v2"
RAW = ROOT / "data/research-v2"
API = "https://api.github.com/repos/nflverse/nflverse-data/releases/tags/pbp"


def check_year(season):
    if type(season) is not int or season not in YEARS:
        raise ValueError("Protected or unsupported season; V2 permits only 2010–2023")


def team(value):
    return ALIASES.get(value, value)


def fetch(url):
    request = Request(url, headers={"User-Agent": "FourthDown-research-v2", "Accept": "application/vnd.github+json" if url == API else "application/octet-stream"})
    with urlopen(request, timeout=90) as response:
        body = response.read(128_000_001)
    if len(body) > 128_000_000:
        raise ValueError("Research asset exceeds bounded download")
    return body


def aggregate(pbp, games, season):
    """Raw observable scrimmage yards; no learned or end-of-season ratings."""
    check_year(season)
    if not set(COLUMNS) <= set(pbp) or not pbp.season.eq(season).all():
        raise ValueError("Missing columns or mixed/protected PBP seasons")
    expected = games[games.season.eq(season) & games.game_type.eq("REG")]
    selected = pbp[pbp.season_type.eq("REG") & pbp.game_id.isin(expected.game_id)]
    rows = []
    for game in expected.sort_values("game_id").itertuples():
        frame = selected[selected.game_id.eq(game.game_id)]
        reason = None
        if frame.empty:
            reason = "missing PBP game"
        elif frame.play_id.isna().any() or frame.play_id.duplicated().any():
            reason = "missing/duplicate play identity"
        plays = frame[frame.play_type.isin(["pass", "run"])].copy()
        for flag in ("qb_kneel", "qb_spike", "two_point_attempt"):
            if not plays[flag].isin([0, 1]).all():
                reason = "invalid scrimmage flag"
        plays = plays[plays.qb_kneel.eq(0) & plays.qb_spike.eq(0) & plays.two_point_attempt.eq(0)]
        plays["posteam"] = plays.posteam.map(team)
        plays["defteam"] = plays.defteam.map(team)
        home, away = team(game.home_team), team(game.away_team)
        if (not plays.posteam.isin([home, away]).all() or not plays.defteam.isin([home, away]).all()
                or plays.posteam.eq(plays.defteam).any()):
            reason = "invalid scrimmage team identity"
        yards = pd.to_numeric(plays.yards_gained, errors="coerce")
        if not np.isfinite(yards).all() or not yards.between(-100, 100).all():
            reason = "invalid scrimmage yards"
        counts = {t: int(plays.posteam.eq(t).sum()) for t in (home, away)}
        if min(counts.values()) < 1:
            reason = reason or "missing scrimmage plays"
        for own, opponent in ((home, away), (away, home)):
            rows.append({"season": season, "game_id": game.game_id, "team": own, "opponent": opponent,
                         "valid": reason is None, "reason": reason or "",
                         "plays": counts[own] if reason is None else None,
                         "yards": float(yards[plays.posteam.eq(own)].sum()) if reason is None else None,
                         "allowed_plays": counts[opponent] if reason is None else None,
                         "allowed_yards": float(yards[plays.posteam.eq(opponent)].sum()) if reason is None else None})
    return pd.DataFrame(rows)


def acquire():
    games, schedule_manifest = load_snapshot()
    if schedule_manifest["sha256"] != SOURCE_SHA:
        raise ValueError("Unapproved schedule snapshot")
    if (DIRECTORY / "data-manifest.json").exists():
        raise FileExistsError("Preserve sealed research inputs; use load_inputs for reruns")
    RAW.mkdir(parents=True, exist_ok=True)
    metadata = json.loads(fetch(API))
    sources, tables = [], []
    for season in YEARS:
        check_year(season)  # before selecting or fetching any bytes
        name = f"play_by_play_{season}.parquet"
        asset = next(a for a in metadata["assets"] if a["name"] == name)
        url = f"https://github.com/nflverse/nflverse-data/releases/download/pbp/{name}"
        if asset["browser_download_url"] != url or not 0 < asset["size"] <= 128_000_000:
            raise ValueError("Unverified release asset URL/size")
        raw_path, receipt_path = RAW / name, RAW / (name + ".receipt.json")
        if raw_path.exists():
            body = raw_path.read_bytes()
            receipt = json.loads(receipt_path.read_text())
        else:
            started = datetime.now(timezone.utc).isoformat()
            body = fetch(url)
            receipt = {"retrieval_started_at": started, "retrieved_at": datetime.now(timezone.utc).isoformat()}
        digest = sha(body)
        if len(body) != asset["size"] or (asset.get("digest") and asset["digest"] != "sha256:" + digest):
            raise ValueError("Release changed or asset checksum mismatch")
        if raw_path.exists() and receipt["sha256"] != digest:
            raise ValueError("Local raw snapshot checksum mismatch")
        if not raw_path.exists():
            receipt["sha256"] = digest
            raw_path.write_bytes(body)
            receipt_path.write_bytes(canonical(receipt))
        parquet = pq.ParquetFile(io.BytesIO(body))
        if parquet.metadata.num_rows > 100_000:
            raise ValueError("Unbounded PBP rows")
        # Inspect the season field before parsing football values.
        if set(parquet.read(columns=["season"]).column("season").to_pylist()) != {season}:
            raise ValueError("Mixed/protected PBP season")
        pbp = parquet.read(columns=COLUMNS).to_pandas()
        table = aggregate(pbp, games, season)
        tables.append(table)
        sources.append({"season": season, "url": url, "asset_id": asset["id"], "sha256": digest,
                        "updated_at": asset["updated_at"], **receipt, "upstream_digest": asset.get("digest"),
                        "verification": "HTTPS release URL and size; local SHA256" if not asset.get("digest") else "GitHub SHA256 matched",
                        "raw_rows": len(pbp),
                        "team_game_rows": len(table), "invalid_team_game_rows": int((~table.valid).sum())})
        print(json.dumps({"season": season, "team_game_rows": len(table), "invalid": int((~table.valid).sum())}), flush=True)
    data = pd.concat(tables, ignore_index=True).sort_values(["season", "game_id", "team"])
    encoded = data.to_csv(index=False, lineterminator="\n", float_format="%.12g").encode()
    (DIRECTORY / "team-games.csv").write_bytes(encoded)
    manifest = {"schema_version": 1, "seasons": list(YEARS), "schedule_sha256": SOURCE_SHA,
                "derived_file": "team-games.csv", "derived_sha256": sha(encoded), "sources": sources,
                "parser_sha256": sha(Path(__file__).read_bytes()), "columns": COLUMNS,
                "attribution": "Derived from nflverse/nflfastR NFL play-by-play; schedules nflverse/Lee Sharpe",
                "license": "CC BY 4.0", "license_url": "https://github.com/nflverse/nflverse-data/blob/main/LICENSE.md",
                "vintage_status": "corrected historical data; original publication times unknown"}
    (DIRECTORY / "data-manifest.json").write_bytes(canonical(manifest))
    return manifest


def load_inputs(directory=DIRECTORY):
    manifest = json.loads((directory / "data-manifest.json").read_bytes())
    if manifest["seasons"] != list(YEARS) or manifest["schedule_sha256"] != SOURCE_SHA:
        raise ValueError("Unapproved research manifest")
    raw = (directory / "team-games.csv").read_bytes()
    if sha(raw) != manifest["derived_sha256"]:
        raise ValueError("Research input checksum mismatch")
    data = pd.read_csv(io.BytesIO(raw), keep_default_na=False)
    if not data.season.isin(YEARS).all():
        raise ValueError("Protected or unsupported derived season")
    return data, manifest


if __name__ == "__main__":
    acquire()
