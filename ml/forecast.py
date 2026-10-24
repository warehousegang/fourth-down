"""Generate historical replay artifacts without fitting or network access."""
import json
import math
from datetime import datetime, timezone

import pandas as pd

from ml.data import ROOT, load_snapshot
from ml.features import LABELS, VERSION, build_features


def score(model, row):
    factors = []
    for key, coefficient in zip(model["features"], model["coefficients"], strict=True):
        feature = key.removesuffix("_diff")
        home, away = float(row[f"home_{feature}"]), float(row[f"away_{feature}"])
        value = float(row[key])
        if not all(math.isfinite(v) for v in (home, away, value, coefficient)):
            raise ValueError("Required feature is missing or non-finite.")
        factors.append({"key": key, "label": LABELS[key], "home": home, "away": away,
                        "difference": value, "coefficient": coefficient, "contribution": value * coefficient})
    z = model["intercept"] + sum(f["contribution"] for f in factors)
    p = 1 / (1 + math.exp(-z))
    return p, factors


def generate():
    games, manifest = load_snapshot()
    model = json.loads((ROOT / "artifacts/model.json").read_text())
    report = json.loads((ROOT / "artifacts/evaluation.json").read_text())
    if model["source_sha256"] != manifest["sha256"] or model["feature_version"] != VERSION:
        raise ValueError("Model does not match source/feature version.")
    if report["source"]["sha256"] != manifest["sha256"] or report["selected"] != model["kind"]:
        raise ValueError("Evaluation and model provenance disagree.")
    features = build_features(games)
    source = games.set_index("game_id")
    output = []
    for _, row in features[features.season.eq(2023)].iterrows():
        game = source.loc[row.game_id]
        cutoff = pd.Timestamp(row.gameday).tz_localize("America/New_York").isoformat()
        kickoff = None
        if pd.notna(game.gametime):
            kickoff = pd.Timestamp(f"{row.gameday} {game.gametime}").tz_localize("America/New_York").isoformat()
        item = {"id": row.game_id, "week": int(row.week), "season": 2023,
                "home": row.home_team, "away": row.away_team, "kickoff": kickoff,
                "cutoff": cutoff, "stadium": str(game.stadium) if pd.notna(game.stadium) else "Venue unavailable",
                "neutral_site": bool(game.location == "Neutral"),
                "history_games": {"home": int(row.home_games), "away": int(row.away_games)},
                "model_id": model["id"], "status": "available", "reason": None,
                "home_probability": None, "factors": []}
        try:
            item["home_probability"], item["factors"] = score(model, row)
        except (ValueError, KeyError) as error:
            item.update(status="unavailable", reason=str(error))
        output.append(item)
    artifact = {"schema_version": 1, "mode": "historical-replay",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "model": model, "evaluation": report, "games": output,
                "attribution": {"name": "nflverse / Lee Sharpe",
                                "url": "https://github.com/nflverse/nflverse-data",
                                "license": "CC BY 4.0", "license_url": "https://creativecommons.org/licenses/by/4.0/"},
                "limitations": ["Historical replay, not a live forecast or a prediction published in 2023.",
                                "Probabilities are conditional on a non-tied result.",
                                "No injury, quarterback, weather, news or play-by-play inputs.",
                                "Schedule data can be retrospectively corrected; no vintage snapshots.",
                                "The model was selected on 2023; validation is not an unbiased final test.",
                                "Designated home advantage also applies at neutral venues."]}
    path = ROOT / "web/public/data/demo.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, separators=(",", ":"), allow_nan=False) + "\n")
    print(f"Generated {len(output)} real historical forecasts; artifact {path.stat().st_size:,} bytes.")


if __name__ == "__main__":
    generate()
