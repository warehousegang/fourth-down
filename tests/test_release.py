"""Checks on review records only; no protected data or fitting."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads((ROOT / path).read_text())


def test_original_and_additive_freezes_remain_intact():
    for name in ("docs/FROZEN_MODEL.json", "docs/HOLDOUT_PROTOCOL_FREEZE.json", "docs/RELEASE_ARTIFACTS.json"):
        for path, expected in read(name)["file_sha256"].items():
            assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected, path


def test_exposure_is_disclosed_without_authorizing_evaluation():
    exposure = read("docs/HOLDOUT_EXPOSURE.json")
    assert exposure["status"] == "partially-exposed"
    assert exposure["observed_aggregate_baseline_metrics"] == {"accuracy": .5359, "brier": .2492, "log_loss": .6915}
    assert exposure["evaluation_authorized"] is False
    assert exposure["candidate_evaluated_in_this_workspace"] is False
    protocol = read("docs/HOLDOUT_PROTOCOL_FREEZE.json")
    assert protocol["execution_authorized"] is False
    assert protocol["original_frozen_files"] == read("docs/FROZEN_MODEL.json")["file_sha256"]
