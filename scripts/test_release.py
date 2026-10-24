"""Run local/CI tests under the explicit no-retraining release restriction."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline


def forbidden_fit(*args, **kwargs):
    raise AssertionError("Fitting is forbidden during corrective release verification")


for cls in (LogisticRegression, StandardScaler, Pipeline):
    cls.fit = forbidden_fit
StandardScaler.partial_fit = forbidden_fit


class NoRetraining:
    def pytest_collection_modifyitems(self, items):
        for item in items:
            if item.name == "test_training_is_repeatable_and_matches_exported_model":
                item.add_marker(pytest.mark.skip(reason="Owner prohibits retraining; frozen hashes and saved-coefficient scoring tested instead"))


if __name__ == "__main__":
    raise SystemExit(pytest.main([str(ROOT / "tests"), str(ROOT / "legacy/test_features.py"), "-q", *sys.argv[1:]], plugins=[NoRetraining()]))
