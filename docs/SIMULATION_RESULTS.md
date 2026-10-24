# RC1 replay and simulation results

These are three different kinds of evidence: retrospective model calculations, synthetic outcome uncertainty, and controlled software scenarios. None is genuine prospective model validation. All new outputs are under ignored `artifacts/rc1/`; none enters the dashboard or its real forecast history.

## Reproduce locally

Run from the repository root with the pinned Python environment (the existing interpreter is `/Users/thomas/Documents/ChatGPT/AI/nfl-predictor/.venv/bin/python`). No command below acquires data or fits a model.

```sh
python -m ml.replay --verify-repeat
python -m ml.simulation --synthetic --probability 0 --count 1000000 --seed 42
python -m ml.simulation --synthetic --probability .5 --count 1000000 --seed 42
python -m ml.simulation --synthetic --probability .8 --count 1000000 --seed 42
python -m ml.simulation --synthetic --probability 1 --count 1000000 --seed 42
python -m ml.simulation --synthetic --probability .8 --count 10000000 --seed 42
python -m ml.simulation --synthetic --forecast forecast-2026-66342f068c048d28b96b456b61d0e51d4cb981a72fce1519d53df24c383aef77.json --game ngs-2026-60272 --count 1000000 --seed 42
python -m ml.lifecycle_simulation
python -m ml.rc1_operations
python scripts/verify_rc1.py
python scripts/test_release.py
```

Replay requires the already authorized local 2010–2023 snapshot and manifest. Current verification requires the preserved 2026 captures. Neither silently downloads missing evidence. A clean source checkout intentionally skips the raw-data-dependent integration cases and the prohibited fitting test. Fixed-input simulation, synthetic scenarios and operational tests remain runnable offline.

## Bernoulli outcome uncertainty

The simulator uses Python MT19937 with seed-version 2, one uniform draw per trial, aggregate O(1) outcome storage and an explicit `--synthetic` flag. It accepts 1–10,000,000 trials and integer seeds 0–2³²−1. Negative/out-of-range/nonfinite probabilities, booleans, noninteger counts/seeds, excessive counts and invalid forecast references fail clearly. A saved forecast is checksum/model/cutoff verified before its p is used. No game scores or real outcome records are created.

| Input p | Draws | Seed | Synthetic wins | Frequency |
|---:|---:|---:|---:|---:|
| 0 | 1,000,000 | 42 | 0 | 0 |
| 0.5 | 1,000,000 | 42 | 499,824 | 0.499824 |
| 0.8 | 1,000,000 | 42 | 800,622 | 0.800622 |
| 1 | 1,000,000 | 42 | 1,000,000 | 1 |
| 0.8 | 10,000,000 | 42 | 8,002,018 | 0.8002018 |
| Saved home p = 0.45329372581401256 | 1,000,000 | 42 | 453,103 | 0.453103 |

Repeated p=0.8 / one-million / seed42 runs produce identical output bytes and SHA256. The exact runtime version and implementation hash are included in each result; changing runtime metadata can change file hashes even when draws agree. The six unique output artifacts and exact CLI arguments are indexed in `artifacts/rc1/monte-carlo/evidence-index.json` and summarized in RC1_VALIDATION.json.

Theoretical frequency standard error is `sqrt(p(1-p)/n)`. At p=.8/n=1M it is .0004. The conservative 95% Hoeffding deviation radius is .00135810 (zero for degenerate p=0/1); all observed test frequencies lie inside their conditional bands. These quantify sampling variation **assuming p is correct and trials are independent**. They exclude parameter error, calibration error, input uncertainty and distribution shift. Agreement between frequency and input p is not model accuracy. The saved NFL probability conditions on a non-tied result; these trials do not simulate ties.

## Controlled lifecycle scenarios

The real frozen scorer processes four earlier fictitious games; fixed margins yield home p=.9228153986996283 for the strong favorite and p=.12643529404838136 for the home underdog. Probabilities are never overwritten. Synthetic final scores are declared test fixtures, unrelated to the Bernoulli output or real NFL results.

| Scenario | Verified behavior |
|---|---|
| Strong favorite loses | Original p preserved; Brier .8515882601, log loss 2.5615553069; loss alone is not a model defect |
| Home underdog wins | Original p preserved; Brier .7631152955, log loss 2.0680246112; no fabricated cause |
| Correct favorite | Correctness and scalar probability-loss oracle agree |
| Missing final | Awaiting result; no invented score or evaluation |
| Postponed | Changed schedule disqualifies the old primary forecast; no fake final |
| Corrected final score | New result/evaluation version; previous forecast/evaluation bytes preserved |
| Late injury | After-cutoff annotation excluded from eligible explanatory evidence; no p adjustment |
| Stale source | Unavailable prediction and explicit warning |
| Missing source | Explicit error; last successful temporary pointer preserved |
| Missing feature input | No zero/default result invented to hide missing history |
| Duplicate event | Same immutable output; one count per eligible final game |
| Failed generation | Failure surfaces without replacing last good pointers |
| In-progress game | No final evaluation based on apparent score |
| Tied final | Explicit exclusion from binary performance metrics |

Fourteen scenarios check 322 named assertions; 31 dedicated tests include no-network/no-fit and path-isolation challenges. All intermediate forecast and operations publication uses temporary directories, with complete payloads captured in a synthetic report. Repeated runs are byte-identical. The scalar oracle independently verifies `(p-y)^2`, `-log(p(observed winner))`, calibration counts, and primary versus all-version populations. Investigations cite observed facts and separate hypotheses requiring evidence; they cannot invent injury, weather or quarterback explanations.

## Retrospective replay

The only independent incumbent evaluation season is 2023: 272 games, accuracy .5882352941, Brier .2370447317 and log loss .6657815065. Confidence intervals, baseline comparisons and calibration are in RC1_RELEASE_REPORT.md / RC1_VALIDATION.json. [RC1_REPLAY_PROTOCOL.md](RC1_REPLAY_PROTOCOL.md) specifies earlier-date state, frozen preprocessing, ties, cutoffs and the publication-vintage limitation. 2024–2025 stays locked and partially exposed. No new training or tuning occurred.
