"""Read-only byte reproduction of a captured forecast; never changes latest pointers."""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ml.current import generate
from ml.current_source import canonical, load_snapshot, sha, timestamp
from ml.refresh import finalize_generation, snapshots_before


def replay(path):
    raw = Path(path).read_bytes()
    artifact = json.loads(raw)
    season = artifact["season"]
    if type(season) is not int or season < 2026:
        raise ValueError("Only non-protected current forecasts can be replayed")
    if not re.fullmatch(r"[a-f0-9]{64}", artifact["snapshot_sha256"]):
        raise ValueError("Invalid source snapshot address")
    if Path(path).name != f"forecast-{season}-{sha(raw)}.json":
        raise ValueError("Forecast content address mismatch")
    for name, digest in artifact["pipeline_sha256"].items():
        if name not in {"ml/current.py", "ml/current_source.py", "ml/refresh.py", "ml/features.py", "ml/forecast.py"}:
            raise ValueError("Unrecognized pipeline path")
        if sha((ROOT/name).read_bytes()) != digest:
            raise ValueError(f"Matching pipeline revision required for {name}; use its recorded Git revision in an isolated checkout")
    snapshot_path = ROOT/f"data/current/{season}/snapshot-{artifact['snapshot_sha256']}.json"
    snapshot = load_snapshot(snapshot_path, season)
    observations = snapshots_before(snapshot_path, season, timestamp(artifact["as_of"]))
    prior = [s for s in observations if timestamp(s["retrieved_at"]) < timestamp(snapshot["retrieved_at"])]
    reconstructed = generate(snapshot, prior, artifact["as_of"], artifact["generated_at"])
    if "ml/refresh.py" in artifact["pipeline_sha256"]:
        reconstructed = finalize_generation(reconstructed, timestamp(artifact["generated_at"]))
    if canonical(reconstructed) != raw:
        raise ValueError("Replayed bytes differ from the immutable forecast")
    return {"forecast":Path(path).name,"sha256":sha(raw),"byte_identical":True,"written_files":0}


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--forecast",type=Path)
    args=parser.parse_args()
    directory=ROOT/"web/public/data/current"
    path=args.forecast or directory/json.loads((directory/"latest.json").read_bytes())["file"]
    print(json.dumps(replay(path),indent=2))
