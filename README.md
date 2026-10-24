# Fourth Down · NFL Predictive Intelligence

A local NFL forecasting and evaluation system: real upcoming probabilities, immutable prediction history, current team/player context, postgame scoring, deterministic investigation and separately versioned challenger research. Python produces checksummed static JSON; React verifies and displays it. **The frozen schedule model remains operational. Nothing has been deployed or promoted.** Start with [the authoritative project record](docs/PROJECT.md), [handoff](docs/HANDOFF.md) and [G0–G4 gate report](docs/RELEASE_GATES.md).

## Open locally

Node 22.14.0/npm 10.9.2 were used. From this project:

```sh
cd web
npm ci --ignore-scripts
npm run dev -- --port 4175 --strictPort
```

Open http://127.0.0.1:4175/. The six product views are Upcoming Games, Matchup Intelligence, Forecast History, Model Intelligence, Postgame Analysis and Architecture. Existing 2023 retrospective matchups/explanations/performance remain separately accessible. Recorded current forecasts expire and suppress probabilities after kickoff; this is not an always-live service. Included static artifacts and notices make a clean checkout browsable without Python, raw data or training.

## Explicit local operations

Use Python 3.14.2 with the unchanged requirements and constraints. This machine's existing interpreter is `/Users/thomas/Documents/ChatGPT/AI/nfl-predictor/.venv/bin/python`; do not alter the original repository/environment.

```sh
# Exact current-season acquisition, frozen inference, history and official-final reconciliation:
python -m ml.refresh
# Advisory only; substitute an actual retained normalized snapshot:
python -m ml.refresh --plan --snapshot data/current/2026/snapshot-<sha>.json
# Independent context-only current annotations; no probability adjustments:
python -m ml.context --season 2026 --snapshot data/current/2026/snapshot-<sha>.json
```

The schedule source is season-isolated SportsDataverse NFL NGS; current injury, QB depth-chart and basic team-stat context comes from season-isolated nflverse assets. Each capture records actual update/retrieval times and hashes. No current acquisition opens 2024–2025. Preserve earlier observations: a first capture after the cutoff cannot prove pregame availability. [OPERATIONS.md](docs/OPERATIONS.md) explains failure bounds, freshness, local evidence bundles, final-forecast selection, result corrections, cost and disabled scheduling. [CURRENT_FORECASTS.md](docs/CURRENT_FORECASTS.md) details the frozen feature contract.

Forecast inputs remain season win rate, scoring margin, recent margin and rest, with exact frozen smoothing/scaling/coefficient definitions. Current context has a separate cutoff and does not change these inputs. Missing injury report times remain unknown; missing reports do not mean healthy; a depth-chart slot does not confirm a starter. Weather, verified news, travel distance and individual QB performance remain unavailable. Real prospective performance is unknown until recorded games finish; the existing schedule's earlier results are not assigned retroactive predictions.

## Verify without fitting

```sh
python scripts/test_release.py
# Read-only byte replay; requires retained current source observations and matching code:
python scripts/replay_current.py
# Independent raw-CSV probabilities/factors:
python scripts/verify_current.py
# Separate retained 2010–2023 source only; no historical acquisition or fitting:
python scripts/recompute_validation.py
cd web
npm test
npm run test:release
VITE_BASE_PATH=/nfl-predictor/ npm run build
VITE_BASE_PATH=/nfl-predictor/ npm run preview -- --port 4174 --strictPort
# In another terminal, using installed Google Chrome:
TEST_BASE_URL=http://127.0.0.1:4174/nfl-predictor/ npm run test:e2e
```

The release runner forbids estimator/scaler fitting and skips the original fit-repeatability test. Raw-data integration tests skip in a clean checkout; synthetic leakage/integrity tests remain active. Frontend tests verify artifact arithmetic and chronology independently. Browser tests cover desktop/mobile, deep links, errors, responsive layout and selected axe checks; they are not exhaustive accessibility certification. Production builds verify every public artifact, original freezes, registry, protocols, dependency notices and Action SHA pins.

## Separate challenger research

The locked directive permits intentional local challenger experiments on approved data. `python -m ml.challenger --verify-repeat` runs only the fixed predeclared experiment in [CHALLENGER_PROTOCOL.md](docs/CHALLENGER_PROTOCOL.md), using the previously preserved hash-verified 2010–2023 CSV. It never downloads historical data or replaces the incumbent. This command fits separate research models and is deliberately excluded from release verification. Re-running is unnecessary to browse the saved experiment.

The actual challenger has ten features across seven schedule-derived domains, six chronological 2018–2023 diagnostic folds, independent prior-season calibration, seven domain ablations, baselines and season-week bootstrap intervals. Its 2023 Brier is 0.23228 versus the frozen incumbent 0.23704, with paired 95% difference interval crossing zero. Pooled historical results compare a contemporaneously refitted incumbent recipe, not the frozen model on its training years; calibration and training-window differences prevent a feature-only interpretation. 2023 was already used for model selection. All results remain research diagnostics.

**No promotion:** a per-season calibration criterion fails, prospective shadow evidence and historical publication vintages are missing, and current 2026 prior strength would require locked 2025 data. [MODEL_REGISTRY.json](docs/MODEL_REGISTRY.json) keeps `schedule-v1-741cf41752` operational. Further changes require a new versioned protocol, measured evidence and explicit owner promotion approval.

## Preservation and approval boundaries

The original five scripts remain unchanged in `legacy/`, with hashes matching `~/Documents/ChatGPT/AI/nfl-predictor`. The owner-selected working project is this separate `~/Documents/ChatGPT/nfl predictor` directory. Do not execute legacy baseline/training scripts, `ml.data`, `ml.train` or the historical all-season loader: they are preserved provenance, not authorized operational entry points.

The candidate coefficients/preprocessing/features, eight frozen files, 2023 replay, validation evidence and holdout protocol/exposure remain unchanged. The locked 2024–2025 period is **partially exposed**: previously observed legacy aggregate accuracy 0.5359, Brier 0.2492 and log loss 0.6915 remain disclosure only. No additional protected results were acquired or evaluated.

The owner controls G0–G4 approvals. Local implementation, current-season scoring and separate bounded challenger research are authorized. Public deployment, recurring scheduled execution, paid services, account changes, personal-site changes, protected holdout use and model promotion require explicit approval. Workflow templates remain inactive and no remote workflow ran. Deterministic investigation is implemented; an LLM research adapter is only a bounded design.

Current schedule attribution: [SportsDataverse](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nfl_ngs_schedules), repository MIT notice in `web/public/CURRENT_DATA_NOTICE.txt`. Historical/current context: [nflverse](https://github.com/nflverse/nflverse-data), historical schedule contribution by Lee Sharpe, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Transformations and predictions are derived modifications. Upstream redistribution/source-code licensing remain public-release review items. Original text team identifiers replace NFL/ESPN logo assets. Full dependency notices ship with the app; see [THIRD_PARTY.md](docs/THIRD_PARTY.md). No affiliation with NFL or nflverse. Educational research, not betting advice.
