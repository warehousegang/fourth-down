# Fourth Down · NFL Predictive Intelligence

A local, reproducible NFL research dashboard. Python builds pre-cutoff current-season state and scores the unchanged frozen model; React displays versioned static forecasts. **Current Week Forecasts is the default screen; 2023 historical analysis stays separate.** The 2024–2025 period is partially exposed; further candidate evaluation is locked. See docs/HOLDOUT_EXPOSURE.json and the separately frozen docs/HOLDOUT_PROTOCOL.md. Nothing has been deployed.

## Open the demonstration
Node 22.14.0 and npm 10.9.2 were used locally. From this project:
```sh
cd web
npm ci --ignore-scripts
npm run dev -- --port 4173
```
Open http://127.0.0.1:4173/. Explore Current Week Forecasts, 2023 Matchups, Prediction explanation, Model performance and Architecture. Current forecasts carry source age, cutoffs and expiry; they are manual snapshots, not a live feed. Select a week/game; URLs retain the selection across refresh. Checksummed current versions, the unchanged 2023 demo and complete notices are included in Git. No Python, raw data, training or data download is needed to browse a clean checkout. Build checks fail if the approved artifact, model freeze, protocol or notices change. See docs/DEPLOYMENT.md.

## Generate upcoming current-week forecasts
From the project root, using the existing Python 3.14.2 environment:
```sh
python -m ml.current
```
This explicitly downloads the current season's SportsDataverse NFL Next Gen Stats schedule, saves immutable local observations under data/current/<season>/, and writes a content-addressed version plus latest.json under web/public/data/current/. The first local capture on October 24, 2026 contains 13 available Week 7 forecasts. Each later refresh uses its actual observation time; it never invents historical availability or reads 2024–2025. Source/coverage errors leave the previous version intact; incomplete team histories and unknown kickoffs produce unavailable reasons. The browser hides expired and past-kickoff probabilities.

See [the current forecasting runbook](docs/CURRENT_FORECASTS.md) for exact reproduction, missing-data behavior and disabled automation. Refresh before game-day midnight Eastern where possible; a first late observation cannot prove earlier availability. Retain local snapshots between refreshes. This command performs no training, evaluation, publication or remote write.

## Verify without retraining
Use Python 3.14.2 with the unchanged dependency constraints. On this machine, the existing interpreter is `/Users/thomas/Documents/ChatGPT/AI/nfl-predictor/.venv/bin/python`; its environment is read only during these checks.
```sh
python scripts/test_release.py
# Local-only independent 2023 reproduction requires the captured data/ and artifacts/:
python scripts/recompute_validation.py
# Independent current-forecast formulas against the captured current-season CSV:
python scripts/verify_current.py
```
The release runner blocks estimator/scaler fitting and explicitly skips the one repeatability test that would retrain. All other local Python tests run, including the preserved legacy feature tests. In a clean checkout, the real-snapshot test also skips because raw data is intentionally excluded. Full training entry points remain preserved for provenance; do not run ml.data, ml.train, ml.forecast, legacy/baseline.py or legacy/train.py during release preparation. Only the new season-isolated ml.current command is authorized to acquire current-season data. Do not use the historical all-season loader or execute the 2024–2025 assessment.

The original frozen model manifest and its eight file hashes are unchanged. HOLDOUT_PROTOCOL_FREEZE.json adds a prospective protocol relative to further inspection, not a claim that earlier model selection or holdout exposure was preregistered. The original legacy baseline previously ran; owner-reported pooled 2024–2025 results were accuracy 0.5359, Brier 0.2492 and log loss 0.6915. They have not been recomputed here.

## Actual 2023 results
Training: 3,347 non-tied regular-season games, 2010–2022. Validation: the same 272 games for all contenders.

| Model | Accuracy | Brier ↓ | Log loss ↓ |
|---|---:|---:|---:|
| 50/50 probability | 55.51% | 0.2500 | 0.6931 |
| Historical home rate | 55.51% | 0.2470 | 0.6871 |
| Original logistic | 55.51% | 0.2453 | 0.6844 |
| Schedule logistic | 58.82% | 0.2370 | 0.6658 |

The 50/50 classification uses p≥0.5 and therefore picks home. Candidate win-rate, margin, recent-margin and rest features use strictly earlier dates; probabilities exclude ties. Paired weekly-bootstrap Brier difference vs home baseline: −0.0099, descriptive 95% interval [−0.0247, +0.0064]. This does **not** establish a reliable improvement. Model selection used 2023. See the dashboard for expanding-window backtests, calibration counts, ablations and limitations.

## Frontend checks
```sh
cd web
npm test
npm run test:release
npm run build
# Start the local server before browser tests. Tests use installed Google Chrome.
npm run test:e2e
# Example GitHub Pages subpath build:
VITE_BASE_PATH=/nfl-predictor/ npm run build
VITE_BASE_PATH=/nfl-predictor/ npm run preview -- --port 4174 --strictPort
# In another terminal:
TEST_BASE_URL=http://127.0.0.1:4174/nfl-predictor/ npm run test:e2e
```
Browser tests cover desktop/mobile flows, refreshed hash URLs, failed data loading and axe accessibility scans. They are authored tests, not a claim of exhaustive accessibility certification. Build artifacts remain ignored.

## Project map
- `legacy/`: five original scripts, untouched, with SHA256 manifest. **Do not run legacy/baseline.py**: it evaluates the protected holdout. `legacy/train.py` also retrieves protected seasons. The new harness reproduces the original model on restricted data.
- `ml/`: explicit acquisition, temporal features, validation-only model comparison and separate forecast generation.
- `web/`: React/TypeScript/Vite, runtime contract, styles, tests and separate current/historical static artifacts.
- `docs/`: product, architecture, data/feature provenance, evaluation, gates, risk register, research boundaries, deployment/rollback and engineering handoff.
- `.github/workflows/ci.yml`: manual-only checks; not run remotely.
- `.github/workflows/current-refresh.yml.disabled`: inactive manual candidate refresh; no cron, commit, deployment or paid infrastructure.
- `.github/workflows/pages.yml.disabled`: inactive deployment preparation, requiring approval.

## Boundaries
Local research is provisionally Tier A. Public release is NO-GO until human approval and licensing/security/cost review. The assignment's supplied Idea-to-Production gates govern this build; the separate full framework source was not available. Research enrichment is design-only; no paid calls, agents, background loops, persistent compute or cloud resources.

Current data: [SportsDataverse NFL Next Gen Stats schedules](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nfl_ngs_schedules), with repository MIT notice in web/public/CURRENT_DATA_NOTICE.txt. Upstream redistribution review remains a public-release gate. Historical data attribution: [nflverse schedules / Lee Sharpe](https://github.com/nflverse/nflverse-data), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Features and predictions are derived modifications. Upstream and trademark rights still require public-release review. The frontend uses original text team identifiers; NFL/ESPN image assets have been retired from the source package and build. Full bundled library notices ship at web/public/THIRD_PARTY_NOTICES.txt. The Python license inventory is in docs/PYTHON_DEPENDENCY_NOTICES.txt; see docs/THIRD_PARTY.md. This project is not affiliated with the NFL or nflverse. Educational research, not betting advice.
