"""Explicit acquisition and immutable local snapshot verification."""
import hashlib
import importlib.metadata
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
COLUMNS = ["game_id", "season", "week", "game_type", "gameday", "gametime",
           "home_team", "away_team", "home_score", "away_score", "stadium", "location"]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def acquire():
    import nflreadpy as nfl
    from nflreadpy.config import update_config
    update_config(cache_mode="off", verbose=False)
    # nflreadpy downloads an all-season asset internally. Do not persist, inspect,
    # summarize or model its protected rows. Restrict immediately at the boundary.
    games = nfl.load_schedules(list(range(2010, 2024))).to_pandas()
    games = games.loc[games.season.between(2010, 2023) & games.game_type.eq("REG"), COLUMNS]
    DATA.mkdir(exist_ok=True)
    path = DATA / "schedules-2010-2023.csv"
    if path.exists():
        raise FileExistsError("Snapshot already exists; preserve it before an explicit reacquisition.")
    games.sort_values("game_id").to_csv(path, index=False)
    manifest = {"source": "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.parquet",
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "sha256": digest(path), "rows": len(games), "seasons": [2010, 2023],
                "python": platform.python_version(),
                "packages": {p: importlib.metadata.version(p) for p in
                             ["numpy", "pandas", "scikit-learn", "nflreadpy"]}}
    (DATA / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


def load_snapshot():
    path = DATA / "schedules-2010-2023.csv"
    manifest = json.loads((DATA / "manifest.json").read_text())
    if digest(path) != manifest["sha256"]:
        raise ValueError("Source checksum mismatch; refusing an unversioned input change.")
    frame = pd.read_csv(path)
    if not frame.season.between(2010, 2023).all():
        raise ValueError("Protected or unsupported season in snapshot.")
    return frame, manifest


if __name__ == "__main__":
    acquire()
