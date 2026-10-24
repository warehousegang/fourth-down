# RC1 historical replay validation

This additive, read-only validation uses the existing hash-verified 2010–2023 regular-season CSV and the unchanged frozen incumbent `schedule-v1-741cf41752`. It evaluates **2023 only**. The incumbent was fitted on 2010–2022 and selected using 2023, so 2023 is a selection-exposed retrospective diagnostic. Earlier fitted seasons are not presented as incumbent backtests. The 2024–2025 holdout remains locked and partially exposed by the previously disclosed legacy baseline aggregates. No acquisition, fitting, tuning, model promotion or public-artifact update is permitted.

The harness independently parses CSV, queries each team's complete, same-season history on strictly earlier calendar dates, reconstructs all four features and evaluates the saved raw-coefficient logistic equation. It does not call the production feature builder, scoring function, training entry point or network. Ties update history by half a win, but are excluded as binary targets; incomplete games do not update state. Calendar-day cutoff is midnight America/New_York. The target, same-date results and later results cannot affect its features. Model preprocessing is already absorbed into saved raw coefficients; no scaler is fitted or reapplied.

**Availability limitation:** the dataset is a corrected historical extract. Event dates determine eligibility, but original publication/completion-observation vintages are absent. This is event-time retrospective replay, not proof that every source value had been published by its historical cutoff and not genuine prospective performance. Missing publication evidence is disclosed rather than fabricated.

Report counts, accuracy at p≥0.5, Brier score, log loss, ten fixed calibration bins, and the sole valid incumbent evaluation season (2023). Recompute the constant .5 and saved-training-population home-win-frequency baselines on identical evaluation rows. Report 2,000 paired bootstrap replicates, seed42, resampling complete `(season, week)` blocks with replacement; the one-year replay has 18 blocks. Use percentile95% intervals for the three metrics and paired Brier differences against the baselines. These intervals are descriptive: one season, repeated teams across weeks, model selection and absent historical vintages limit inference. Calibration bins assess reliability descriptively and do not imply a fitted calibration transform.

Every reconstructed game, timestamp, historical-game count, feature value, coefficient, contribution and probability is compared against the preserved historical artifact. Historical cutoff is not substituted with today's capture time. Immutable source/freeze/demo hashes and frozen-file checks are recorded. Optional saved challenger validation recomputes existing 2018–2023 prediction arithmetic, metrics and train/calibration/evaluation boundaries without fitting; it does not independently reproduce the challenger's fitting procedure or establish unseen-test performance.

Run from the project root using its pinned Python environment:

```sh
python -m ml.replay --verify-repeat
python -m pytest tests/test_replay.py -q
```

The command requires the separately preserved local CSV and its manifest; it does not download them when absent. Only the real-source integration test skips when that approved snapshot is unavailable in a clean checkout. Synthetic leakage, integrity, no-fit, and saved-artifact checks remain active. Machine-readable evidence is written exclusively under ignored `artifacts/rc1/replay/`, content-addressed by SHA256, with no public pointer or model/registry/evidence replacement. A repeated run compares the deterministic payload, excluding only execution timestamps. These results support RC1 review and do not authorize deployment or holdout execution.
