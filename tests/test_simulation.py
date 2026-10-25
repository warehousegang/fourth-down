"""Synthetic sampling tests plus read-only checks of permitted immutable forecasts."""
import copy
import hashlib
import json
import math
import random
import tracemalloc
from pathlib import Path

import pytest

from ml import simulation


@pytest.mark.parametrize("p,expected", [(0, 0), (1, 3000)])
def test_endpoints_are_exact_but_still_record_requested_trials(p, expected):
    result = simulation.simulate(p, 3000, 42)
    assert result["wins"] == expected
    assert result["losses"] == 3000 - expected
    assert result["observed_win_frequency"] == p
    assert result["conditional_moments"]["frequency_standard_error"] == 0
    assert result["sampling_uncertainty"]["frequency_low"] == p
    assert result["sampling_uncertainty"]["frequency_high"] == p
    assert result["draw_count"] == 3000


@pytest.mark.parametrize("p", [.5, .8])
def test_frequency_matches_fixed_probability_with_sampling_uncertainty(p):
    result = simulation.simulate(p, 100_000, 42)
    assert abs(result["observed_win_frequency"] - p) < result["sampling_uncertainty"]["radius"]
    assert result["conditional_moments"]["bernoulli_variance"] == p * (1 - p)
    assert result["conditional_moments"]["expected_wins"] == 100_000 * p
    assert result["conditional_moments"]["frequency_standard_error"] == math.sqrt(p * (1 - p) / 100_000)
    assert result["wins"] + result["losses"] == result["draw_count"]


def test_same_seed_reproduces_identical_bytes_and_independent_stream():
    first = simulation.simulate(.8, 20_000, 391)
    second = simulation.simulate(.8, 20_000, 391)
    generator = random.Random(391)
    expected = sum(generator.random() < .8 for _ in range(20_000))
    assert first["wins"] == expected
    assert simulation.canonical(first) == simulation.canonical(second)
    assert first["wins"] != simulation.simulate(.8, 20_000, 392)["wins"]


def test_seed_zero_and_maximum_work_without_using_global_random_state():
    previous = random.getstate()
    random.seed(54)
    state = random.getstate()
    assert simulation.simulate(.5, 1000, 0)["seed"] == 0
    assert simulation.simulate(.5, 1000, simulation.MAX_SEED)["seed"] == simulation.MAX_SEED
    assert random.getstate() == state
    random.setstate(previous)


def test_large_count_uses_bounded_outcome_memory():
    tracemalloc.start()
    result = simulation.simulate(.8, 1_000_000, 42)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert result["draw_count"] == 1_000_000
    assert peak < 1_000_000  # A million retained Python results would exceed this by orders of magnitude.
    assert abs(result["observed_win_frequency"] - .8) < .002


def test_maximum_bounded_count():
    result = simulation.simulate(.5, simulation.MAX_COUNT, 42)
    assert result["wins"] + result["losses"] == simulation.MAX_COUNT
    assert abs(result["observed_win_frequency"] - .5) < .001


@pytest.mark.parametrize("p", [True, False, None, "0.5", -0.01, 1.01, float("nan"), float("inf"), -float("inf"), [], {}, 10**1000, -(10**1000)])
def test_invalid_probabilities_fail_before_sampling(p, monkeypatch):
    monkeypatch.setattr(simulation.random, "Random", lambda: pytest.fail("Invalid input must not begin sampling"))
    with pytest.raises(ValueError, match="Probability"):
        simulation.simulate(p, 10, 42)


@pytest.mark.parametrize("count", [True, False, 0, -1, 1.0, "100", None, float("nan"), float("inf"), simulation.MAX_COUNT + 1])
def test_invalid_draw_counts(count):
    with pytest.raises(ValueError, match="Count"):
        simulation.simulate(.5, count, 42)


@pytest.mark.parametrize("seed", [True, False, -1, 42.0, "42", None, float("nan"), float("inf"), simulation.MAX_SEED + 1])
def test_invalid_seeds(seed):
    with pytest.raises(ValueError, match="Seed"):
        simulation.simulate(.5, 10, seed)


def test_sampling_bound_is_about_assumed_probability_not_model_accuracy():
    result = simulation.simulate(.8, 1000, 42)
    assert result["mode"] == "synthetic-bernoulli" and result["synthetic"] is True
    assert "not a confidence interval for the model" in result["sampling_uncertainty"]["interpretation"]
    assert any("does not validate the model" in text for text in result["limitations"])
    assert not {"home_score", "away_score", "accuracy", "brier", "log_loss"}.intersection(result)
    expected_radius = math.sqrt(math.log(40) / 2000)
    assert result["sampling_uncertainty"]["radius"] == expected_radius


def test_immutable_local_write_is_idempotent_and_rejects_corruption(tmp_path, monkeypatch):
    monkeypatch.setattr(simulation, "OUTPUT_DIRECTORY", tmp_path / "monte-carlo")
    result = simulation.simulate(.8, 1000, 42)
    path = simulation.write_result(result)
    before = path.read_bytes(), path.stat().st_mtime_ns
    assert simulation.write_result(result) == path
    assert before == (path.read_bytes(), path.stat().st_mtime_ns)
    path.write_text("corrupt")
    with pytest.raises(ValueError, match="overwrite"):
        simulation.write_result(result)


def test_output_is_fixed_to_ignored_area_and_requires_synthetic_label(tmp_path, monkeypatch):
    assert simulation.OUTPUT_DIRECTORY == simulation.ROOT / "artifacts/rc1/monte-carlo"
    monkeypatch.setattr(simulation, "OUTPUT_DIRECTORY", tmp_path / "output")
    with pytest.raises(ValueError, match="explicitly synthetic"):
        simulation.write_result({"mode": "real-result", "synthetic": False})
    target = tmp_path / "target"
    target.mkdir()
    simulation.OUTPUT_DIRECTORY.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        simulation.write_result(simulation.simulate(.5, 10, 42))


@pytest.fixture
def forecast():
    directory = simulation.FORECAST_DIRECTORY
    # Exercise a retained positive example even when the latest refresh correctly
    # has no available predictions (stale source, postgame or offseason).
    path = directory / "forecast-2026-3449f56cda00dca8e4f4c253458d471b8924cc3ec9a25fd4a5821d356d7737cb.json"
    artifact = json.loads(path.read_text())
    game = next(game for game in artifact["games"] if game["status"] == "available")
    return path, artifact, game


def test_real_saved_model_probability_is_reproduced_without_network_or_writes(forecast, monkeypatch):
    path, artifact, game = forecast
    from ml import current_source
    monkeypatch.setattr(current_source, "acquire", lambda *_: pytest.fail("Simulation must not acquire data"))
    paths = [path, simulation.FORECAST_DIRECTORY / "latest.json", simulation.ROOT / "docs/FROZEN_MODEL.json", simulation.ROOT / "web/public/data/demo.json"]
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    p, source = simulation.load_forecast_probability(path, game["id"])
    model = artifact["model"]
    z = model["intercept"] + sum(c * game["features"][f] for c, f in zip(model["coefficients"], model["features"]))
    assert abs(p - 1 / (1 + math.exp(-z))) < 1e-12
    away, _ = simulation.load_forecast_probability(path.name, game["id"], "away")
    assert away == 1 - p
    assert source["artifact_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert source["model_id"] == "schedule-v1-741cf41752"
    assert source["features"] == game["features"]
    assert source["origin"] == "checksum-and-model-verified-saved-forecast"
    assert before == {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


@pytest.mark.parametrize("name", ["forecast-2024-" + "a" * 64 + ".json", "forecast-2025-" + "a" * 64 + ".json", "latest.json", "games.csv"])
def test_protected_or_nonimmutable_inputs_rejected_before_any_read(name, monkeypatch):
    monkeypatch.setattr(Path, "read_bytes", lambda *_: pytest.fail("Disallowed file must not be read"))
    with pytest.raises(ValueError, match="immutable"):
        simulation.load_forecast_probability(name, "ngs-2026-test")


def write_test_forecast(tmp_path, monkeypatch, artifact):
    monkeypatch.setattr(simulation, "FORECAST_DIRECTORY", tmp_path)
    body = simulation.canonical(artifact)
    path = tmp_path / f"forecast-2026-{simulation.checksum(body)}.json"
    path.write_bytes(body)
    return path


def test_checksum_mismatch_rejected_before_probability_use(forecast, tmp_path, monkeypatch):
    path, _, game = forecast
    monkeypatch.setattr(simulation, "FORECAST_DIRECTORY", tmp_path)
    changed = tmp_path / path.name
    changed.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="checksum"):
        simulation.load_forecast_probability(changed, game["id"])


@pytest.mark.parametrize("mutation", ["model", "probability", "feature", "kickoff", "source", "history", "unavailable"])
def test_saved_forecast_tampering_or_ineligibility_fails(forecast, tmp_path, monkeypatch, mutation):
    _, original, original_game = forecast
    artifact = copy.deepcopy(original)
    game = next(game for game in artifact["games"] if game["id"] == original_game["id"])
    if mutation == "model":
        artifact["model"]["coefficients"][0] += 1
    elif mutation == "probability":
        game["home_probability"] = .99
    elif mutation == "feature":
        game["features"]["smooth_win_diff"] += 1
    elif mutation == "kickoff":
        game["generated_at"] = game["kickoff"]
        artifact["generated_at"] = game["kickoff"]
    elif mutation == "source":
        artifact["source"]["retrieved_at"] = game["kickoff"]
    elif mutation == "history":
        game["history"]["home"][0]["observed_at"] = game["cutoff"]
    else:
        game.update(status="unavailable", home_probability=None, away_probability=None, features={}, factors=[], reason="Test missing data")
    path = write_test_forecast(tmp_path, monkeypatch, artifact)
    with pytest.raises(ValueError):
        simulation.load_forecast_probability(path, game["id"])


def test_unknown_game_side_path_and_oversized_artifact_rejected(forecast, tmp_path, monkeypatch):
    path, artifact, game = forecast
    with pytest.raises(ValueError, match="exactly once"):
        simulation.load_forecast_probability(path, "ngs-2026-missing")
    with pytest.raises(ValueError, match="Side"):
        simulation.load_forecast_probability(path, game["id"], "winner")
    outside = tmp_path / path.name
    outside.write_bytes(path.read_bytes())
    with pytest.raises(ValueError, match="regular immutable"):
        simulation.load_forecast_probability(outside, game["id"])
    monkeypatch.setattr(simulation, "FORECAST_DIRECTORY", tmp_path)
    monkeypatch.setattr(simulation, "MAX_ARTIFACT_BYTES", 3)
    with pytest.raises(ValueError, match="bounded artifact size"):
        simulation.load_forecast_probability(outside, game["id"])


def test_cli_requires_explicit_synthetic_mode_and_rejects_invalid_flags(tmp_path, monkeypatch):
    monkeypatch.setattr(simulation, "OUTPUT_DIRECTORY", tmp_path / "monte-carlo")
    for args in (["--probability", ".8"], ["--synthetic", "--probability", "nan"], ["--synthetic", "--probability", ".8", "--count", "true"], ["--synthetic", "--probability", ".8", "--seed", "-1"], ["--synthetic", "--probability", ".8", "--game", "ngs-2026-test"], ["--synthetic", "--forecast", "missing"]):
        with pytest.raises(SystemExit) as error:
            simulation.main(args)
        assert error.value.code == 2
    assert not simulation.OUTPUT_DIRECTORY.exists()


def test_cli_produces_only_ignored_synthetic_result(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(simulation, "OUTPUT_DIRECTORY", tmp_path / "monte-carlo")
    result = simulation.main(["--synthetic", "--probability", ".8", "--count", "1000", "--seed", "42"])
    output = json.loads(capsys.readouterr().out)
    assert output["mode"] == "synthetic-bernoulli"
    assert result["input"]["origin"] == "explicit-assumed-probability"
    assert len(list(simulation.OUTPUT_DIRECTORY.glob("*.json"))) == 1
