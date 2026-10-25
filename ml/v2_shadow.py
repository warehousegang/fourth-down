"""Local-only paired research ledger. Current V2 is disabled; no production imports/writes."""
import argparse
import json
import math
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from ml.challenger import canonical, frozen_model, predict, sha
from ml.data import ROOT, load_snapshot
from ml.v2_data import DIRECTORY as RESEARCH, load_inputs
from ml.v2_experiment import immutable
from ml.v2_features import FEATURES, build_features

DIRECTORY = ROOT / "data/research-v2/shadow"


def timestamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timezone-aware timestamp required")
    return result


def readiness(season, inputs_available=False):
    if type(season) is not int or season in (2024, 2025) or season - 1 in (2024, 2025):
        return {"enabled": False, "reason": "Protected season or protected previous-season input"}
    # No approved prospective adapter exists in this experiment, even if a caller claims availability.
    return {"enabled": False, "reason": "No approved point-in-time shadow input adapter; research replay only"}


def create_replay_pair(row, model, source_manifest_sha256, kickoff):
    """Pair actual saved features with both models, explicitly retrospective, never backdated."""
    if row["season"] not in range(2011, 2024):
        raise ValueError("Protected or unsupported replay season")
    if not row["eligible"] or not timestamp(row["cutoff"]) < timestamp(kickoff):
        raise ValueError("Unavailable feature state or invalid pregame cutoff")
    if model.get("feature_version") != "v2-efficiency-1" or model["features"] != FEATURES:
        raise ValueError("Wrong V2 model")
    if (model["fit_seasons"][1] >= row["season"] or model["calibration"]["season"] >= row["season"]
            or row["season"] != 2023):
        raise ValueError("Paired frozen-V1/final-V2 replay limited to out-of-fit 2023")
    if (len(source_manifest_sha256) != 64 or any(c not in "0123456789abcdef" for c in source_manifest_sha256)
            or any(not math.isfinite(float(row[f])) for f in FEATURES)
            or any(day >= row["gameday"] for day in row["history_dates"])):
        raise ValueError("Invalid feature provenance or history")
    incumbent = frozen_model()
    frame = pd.DataFrame([row])
    return {"schema_version": 1, "mode": "retrospective-paired-replay", "prospective": False,
            "game_id": row["game_id"], "season": row["season"], "week": row["week"],
            "home_team": row["home_team"], "away_team": row["away_team"],
            "kickoff": kickoff, "cutoff": row["cutoff"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_manifest_sha256": source_manifest_sha256,
            "features": {f: float(row[f]) for f in FEATURES}, "history_ids": row["history_ids"],
            "models": {"v1": {"id": incumbent["id"], "model_sha256": sha(canonical(incumbent)),
                                "probability": float(predict(incumbent, frame)[0])},
                       "v2": {"id": model["id"], "model_sha256": sha(canonical(model)),
                                "probability": float(predict(model, frame)[0])}},
            "limitations": ["Corrected historical feature snapshot, not publication-vintage proof",
                            "Not eligible for the production prospective scorecard"]}


def write_record(record, kind="forecast", directory=DIRECTORY):
    directory = Path(directory).resolve()
    # Only the research ledger or isolated test scratch space, never site/operational paths.
    if not (directory == DIRECTORY.resolve() or DIRECTORY.resolve() in directory.parents
            or (Path(tempfile.gettempdir()).resolve() in directory.parents and ROOT.resolve() not in directory.parents)):
        raise ValueError("V2 ledger writes require an isolated research path")
    if kind not in {"forecast", "reconciliation"}:
        raise ValueError("Unknown research record kind")
    body = canonical(record)
    path = directory / kind / (sha(body) + ".json")
    immutable(path, body)
    return {"file": str(path), "sha256": sha(body)}


def read_record(receipt):
    path = Path(receipt["file"])
    body = path.read_bytes()
    if sha(body) != receipt["sha256"] or path.name != receipt["sha256"] + ".json":
        raise ValueError("Research record checksum mismatch")
    return json.loads(body)


def reconcile_pair(receipt, result):
    """Score both archived probabilities without mutating either forecast or prior results."""
    if receipt.get("mode") != "retrospective-paired-replay" or receipt.get("prospective") is not False:
        raise ValueError("Unsupported record; current prospective shadow remains disabled")
    if receipt["season"] in (2024, 2025) or receipt["season"] != 2023:
        raise ValueError("Protected or unsupported reconciliation season")
    for key in ("game_id", "season", "home_team", "away_team", "kickoff"):
        if result.get(key) != receipt[key]:
            raise ValueError("Changed schedule identity requires review")
    if (result.get("status") != "FINAL" or not result.get("verified")
            or not timestamp(receipt["kickoff"]) < timestamp(result["observed_at"])
            or not timestamp(result["observed_at"]) <= datetime.now(timezone.utc)
            or len(result.get("source_sha256", "")) != 64):
        raise ValueError("Unverified completed result")
    for side in ("home", "away"):
        if type(result.get(side + "_score")) is not int or not 0 <= result[side + "_score"] <= 200:
            raise ValueError("Invalid result score")
    tied = result["home_score"] == result["away_score"]
    y = int(result["home_score"] > result["away_score"])
    scores = {}
    for key, model in receipt["models"].items():
        p = model["probability"]
        if not isinstance(p, (float, int)) or not math.isfinite(p) or not 0 <= p <= 1:
            raise ValueError("Invalid archived probability")
        scores[key] = None if tied else {"correct": (p >= .5) == bool(y), "brier": (p-y)**2,
            "log_loss": -math.log(max(1e-15, p if y else 1-p))}
    return {"schema_version": 1, "mode": "retrospective-paired-reconciliation", "prospective": False,
            "forecast_sha256": sha(canonical(receipt)), "result": result, "scores": scores,
            "excluded_reason": "tie" if tied else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--replay-game", help="Explicit 2023 paired historical replay; never a prospective forecast")
    args = parser.parse_args()
    if not args.replay_game:
        print(json.dumps(readiness(args.season), indent=2))
        return
    if not args.replay_game.startswith("2023_"):
        raise ValueError("Only approved out-of-fit 2023 paired replay is supported")
    receipts = [json.loads(p.read_bytes()) for p in RESEARCH.glob("receipt-*.json")]
    receipt = max(receipts, key=lambda r: r["completed_at"])
    body = (RESEARCH / receipt["result_file"]).read_bytes()
    if sha(body) != receipt["sha256"]:
        raise ValueError("V2 experiment checksum mismatch")
    research = json.loads(body)
    games, source = load_snapshot()
    totals, manifest = load_inputs()
    if research["source"] != manifest or source["sha256"] != manifest["schedule_sha256"]:
        raise ValueError("Research source mismatch")
    row = build_features(games, totals).set_index("game_id").loc[args.replay_game].to_dict()
    row["game_id"] = args.replay_game
    game = games.set_index("game_id").loc[args.replay_game]
    kickoff = datetime.fromisoformat(str(game.gameday) + "T" + str(game.gametime)).replace(tzinfo=ZoneInfo("America/New_York")).isoformat()
    pair = create_replay_pair(row, research["model"], sha(canonical(manifest)), kickoff)
    forecast_receipt = write_record(pair)
    saved = read_record(forecast_receipt)
    final = {k: saved[k] for k in ("game_id", "season", "home_team", "away_team", "kickoff")}
    final.update(status="FINAL", verified=True, home_score=int(game.home_score), away_score=int(game.away_score),
                 observed_at=source["retrieved_at"], source_sha256=source["sha256"],
                 vintage="corrected historical snapshot; not prospective")
    reconciliation = write_record(reconcile_pair(saved, final), "reconciliation")
    print(json.dumps({"mode": saved["mode"], "forecast": forecast_receipt, "reconciliation": reconciliation,
                      "shadow_2026": readiness(2026)}, indent=2))


if __name__ == "__main__":
    main()
