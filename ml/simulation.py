"""Bounded synthetic Bernoulli experiments; no fitting, acquisition or real outcome scoring.

Examples (all outputs stay in ignored artifacts/rc1/monte-carlo):
    python -m ml.simulation --synthetic --probability 0.8 --count 1000000 --seed 42
    python -m ml.simulation --synthetic --forecast forecast-2026-<sha>.json --game ngs-2026-60272 --count 1000000 --seed 42

The supplied probability is assumed, not validated, by these random draws. Each
win/loss is synthetic and conditional on that fixed probability (and on no tie
for the saved NFL model). No simulated result is published to forecast history.
"""
import argparse
import hashlib
import json
import math
import platform
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORECAST_DIRECTORY = ROOT / "web/public/data/current"
OUTPUT_DIRECTORY = ROOT / "artifacts/rc1/monte-carlo"
MAX_COUNT = 10_000_000
MAX_SEED = 2**32 - 1
MAX_ARTIFACT_BYTES = 1_000_000
ALPHA = 0.05


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def checksum(body):
    return hashlib.sha256(body).hexdigest()


def validate(probability, count, seed):
    if type(probability) not in (int, float) or not 0 <= probability <= 1 or not math.isfinite(probability):
        raise ValueError("Probability must be a finite number in [0, 1]; booleans are forbidden")
    if type(count) is not int or not 1 <= count <= MAX_COUNT:
        raise ValueError(f"Count must be an integer in [1, {MAX_COUNT}]; booleans are forbidden")
    if type(seed) is not int or not 0 <= seed <= MAX_SEED:
        raise ValueError(f"Seed must be an integer in [0, {MAX_SEED}]; booleans are forbidden")


def simulate(probability, count, seed):
    """Use one 53-bit random() uniform per trial, without retaining individual draws."""
    validate(probability, count, seed)
    p = 0.0 if probability == 0 else float(probability)
    generator = random.Random()
    generator.seed(seed, version=2)
    wins = sum(generator.random() < p for _ in range(count))
    frequency = wins / count
    variance = p * (1 - p)
    radius = math.sqrt(math.log(2 / ALPHA) / (2 * count)) if variance else 0.0
    return {
        "schema_version": 1, "mode": "synthetic-bernoulli", "synthetic": True,
        "probability": p, "seed": seed, "draw_count": count,
        "wins": wins, "losses": count - wins, "observed_win_frequency": frequency,
        "frequency_minus_input_probability": frequency - p,
        "algorithm": {
            "prng": "Python random.Random / MT19937", "seed_version": 2,
            "trial": "One random() uniform in [0,1) per trial; win iff uniform < input probability",
            "storage": "Aggregate counts only; O(1) outcome memory", "max_draw_count": MAX_COUNT,
            "python_version": platform.python_version(),
        },
        "conditional_moments": {
            "bernoulli_mean": p, "bernoulli_variance": variance,
            "expected_wins": count * p, "win_count_variance": count * variance,
            "win_count_standard_deviation": math.sqrt(count * variance),
            "frequency_standard_error": math.sqrt(variance / count),
        },
        "sampling_uncertainty": {
            "assumed_probability_fixed": True, "coverage": 1 - ALPHA,
            "method": "Hoeffding frequency-deviation bound; exact degenerate interval at p=0 or p=1",
            "radius": radius, "frequency_low": max(0.0, p - radius), "frequency_high": min(1.0, p + radius),
            "observed_frequency_within_bound": abs(frequency - p) <= radius,
            "interpretation": "A bound on Monte Carlo sampling fluctuation under independent Bernoulli trials at the supplied p; not a confidence interval for the model's real-world accuracy or true game probability.",
        },
        "limitations": [
            "All wins and losses in this artifact are simulated, not real NFL outcomes. No game scores are generated.",
            "Simulation assumes a fixed win probability. Matching simulated frequency to that probability does not validate the model, its calibration or predictive accuracy.",
            "Sampling uncertainty excludes parameter uncertainty, input uncertainty, injuries, calibration error and distribution shift.",
            "Saved frozen-model probabilities are conditional on a non-tied outcome. These Bernoulli trials do not simulate ties.",
            "The PRNG is deterministic research tooling, not a source of cryptographic randomness; the sampling bound describes the assumed independent Bernoulli process.",
        ],
        "implementation_sha256": checksum(Path(__file__).read_bytes()),
    }


def load_forecast_probability(path, game_id, side="home"):
    """Read only a named immutable current artifact; validate its saved model and cutoff.

    This does not read any game outcomes or reconstruct features from raw results.
    Independent raw-input reproduction belongs to the RC1 replay harness.
    """
    path = Path(path)
    match = re.fullmatch(r"forecast-(20\d{2})-([0-9a-f]{64})\.json", path.name)
    if not match or int(match[1]) < 2026:
        raise ValueError("Only immutable 2026-or-later current forecast artifacts are permitted")
    if not path.is_absolute() and path.parent == Path("."):
        path = FORECAST_DIRECTORY / path
    if FORECAST_DIRECTORY.is_symlink() or path.is_symlink() or path.parent.resolve() != FORECAST_DIRECTORY.resolve():
        raise ValueError("Forecast must be a regular immutable file in web/public/data/current")
    if not path.is_file() or path.stat().st_size > MAX_ARTIFACT_BYTES:
        raise ValueError("Forecast is missing or exceeds the bounded artifact size")
    with path.open("rb") as stream:
        body = stream.read(MAX_ARTIFACT_BYTES + 1)
    if len(body) > MAX_ARTIFACT_BYTES:
        raise ValueError("Forecast exceeds the bounded artifact size")
    if checksum(body) != match[2]:
        raise ValueError("Forecast checksum differs from its immutable filename")
    if type(game_id) is not str or not game_id.startswith(f"ngs-{match[1]}-"):
        raise ValueError("Game ID must belong to the permitted forecast season")
    if side not in ("home", "away"):
        raise ValueError("Side must be home or away")
    try:
        artifact = json.loads(body)
        if type(artifact["season"]) is not int or artifact["season"] != int(match[1]):
            raise ValueError("Forecast season differs from its immutable filename")
        # Imports are deliberately deferred: raw-probability simulation uses only stdlib.
        from ml.current_source import timestamp
        from ml.lifecycle import eligibility, verify_forecast
        from ml.current import MODEL_FREEZE_SHA
        bundle = {"file": path.name, "sha256": match[2], "artifact": artifact}
        verify_forecast(bundle, artifact["season"], timestamp(artifact["generated_at"]))
        games = [game for game in artifact["games"] if game["id"] == game_id]
        if len(games) != 1:
            raise ValueError("Requested game must occur exactly once in the saved artifact")
        game = games[0]
        # Compare original receipt to its own recorded schedule; no live schedule is consulted.
        original_schedule = {**game, "phase": game.get("source_phase")}
        reasons = eligibility(game, artifact, original_schedule)
        if reasons:
            raise ValueError("Saved forecast is not eligible pregame evidence: " + "; ".join(reasons))
        p = game[f"{side}_probability"]
        validate(p, 1, 0)
        return float(p), {
            "origin": "checksum-and-model-verified-saved-forecast", "file": path.name,
            "artifact_sha256": match[2], "model_freeze_sha256": MODEL_FREEZE_SHA,
            "model_id": artifact["model"]["id"], "season": artifact["season"], "game_id": game_id,
            "side": side, "home": game["home"], "away": game["away"],
            "kickoff": game["kickoff"], "forecast_generated_at": game["generated_at"],
            "cutoff": game["cutoff"], "original_valid_until": artifact["valid_until"],
            "features": game["features"], "source": artifact["source"],
            "notice": "An archived pregame model estimate reused for synthetic trials. Current freshness is not claimed; no result has been retrieved or evaluated.",
            "validation_scope": ["Immutable artifact bytes", "Original frozen model and source-code hashes", "Stored feature/coefficient probability arithmetic", "Original pregame source and history timestamp eligibility"],
        }
    except (KeyError, TypeError, IndexError, json.JSONDecodeError) as error:
        raise ValueError("Malformed saved forecast artifact") from error


def write_result(result):
    """Append one content-addressed ignored result; never touch public artifact pointers."""
    if result.get("mode") != "synthetic-bernoulli" or result.get("synthetic") is not True:
        raise ValueError("Only explicitly synthetic simulation results may be written")
    for folder in (OUTPUT_DIRECTORY, *OUTPUT_DIRECTORY.parents):
        if folder.is_symlink():
            raise ValueError("Simulation output cannot use a symlinked directory")
        if folder == ROOT:
            break
    body = canonical(result)
    target = OUTPUT_DIRECTORY / f"simulation-{checksum(body)}.json"
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("xb") as stream:
            stream.write(body)
    except FileExistsError:
        if target.is_symlink() or target.read_bytes() != body:
            raise ValueError("Refusing to overwrite a changed immutable simulation result")
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--synthetic", action="store_true", required=True, help="Acknowledge that all generated outcomes are synthetic")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--probability", type=float, help="Fixed assumed probability in [0,1]")
    source.add_argument("--forecast", help="Immutable forecast filename or path inside web/public/data/current")
    parser.add_argument("--game", help="Exact current-season game ID, required with --forecast")
    parser.add_argument("--side", choices=("home", "away"), default="home")
    parser.add_argument("--count", "--draws", dest="count", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    try:
        # Reject invalid bounded execution arguments before reading any input artifact.
        validate(0.5 if args.forecast else args.probability, args.count, args.seed)
        if args.forecast:
            if not args.game:
                raise ValueError("--game is required with --forecast")
            p, provenance = load_forecast_probability(args.forecast, args.game, args.side)
        else:
            if args.game or args.side != "home":
                raise ValueError("--game and --side are only meaningful with --forecast")
            p, provenance = args.probability, {"origin": "explicit-assumed-probability", "notice": "User-supplied synthetic scenario, not a real NFL prediction"}
        result = simulate(p, args.count, args.seed)
        result["input"] = provenance
        target = write_result(result)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(json.dumps({"mode": result["mode"], "file": str(target), "probability": result["probability"], "seed": result["seed"], "draw_count": result["draw_count"], "wins": result["wins"], "losses": result["losses"], "frequency": result["observed_win_frequency"], "frequency_standard_error": result["conditional_moments"]["frequency_standard_error"]}, indent=2))
    return result


if __name__ == "__main__":
    main()
