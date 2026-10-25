# Controlled V2 local rehearsal — October 25, 2026

**Complete for review. Recurring V2 execution, deployment and promotion remain disabled.**

This record supplements the original preparation protocol; it does not rewrite its historical authorization or the frozen holdout manifests. The owner explicitly approved 2025 REG score-only priors and this single local rehearsal. See append-only [authorization](../../../docs/holdout-amendments/001-2026-10-25-v2-prior-authorization.json) and [actual exposure](../../../docs/holdout-amendments/002-2026-10-25-v2-prior-exposure.json). 2025 is now consumed operational feature data; the 2024–2025 assessment remains partially exposed and locked. No 2024 source, 2025 PBP, holdout evaluation, fitting, calibration or selection occurred.

The 2025-only SportsDataverse source contains 334 rows: 272 validated final REG games (September 4, 2025 through January 4, 2026), 49 PRE and 13 POST. Non-REG score fields were ignored. All 32 teams have 17 games; the frozen prior is each team’s cumulative scoring margin divided by 21. Full team aggregates, IDs, source URLs, upstream/local hashes and timestamps are in [the evidence](rehearsal-2026-10-25.json).

The 2026 schedule contains 321 rows (272 REG, 49 PRE). All 94 observed completed REG games join to the 16,551-row, 2026-only nflverse PBP capture, yielding 188 team-game totals with no missing completed-game joins. Both current captures were retrieved at 09:35 EDT. Schedule publication remains October 23 at 07:47:43 EDT; PBP publication is October 25 at 05:03:15 EDT. Neither timestamp was rewritten.

The actual shared cutoff was **09:38:07.065309 EDT**. Forecasts completed between **09:38:07.382862 and 09:38:10.735371 EDT**, before their kickoffs. This is an ad hoc rehearsal, explicitly `prospective:false` and `scorecard_eligible:false`; it does not pretend to meet the separately declared T−60 collection window. The unchanged seven-feature model is `v2-efficiency-ff72f16c5ea3`, with pinned raw coefficients, absorbed StandardScaler, 2022 Platt calibration and threshold 0.5.

| Matchup (away @ home) | Away win | Home win |
|---|---:|---:|
| SF @ ATL | 66.9533% | 33.0467% |
| CIN @ BAL | 38.1655% | 61.8345% |
| TB @ CAR | 31.8664% | 68.1336% |
| NYG @ HOU | 33.0437% | 66.9563% |
| IND @ MIN | 31.6795% | 68.3205% |
| MIA @ NYJ | 42.0286% | 57.9714% |
| CLE @ TEN | 57.3635% | 42.6365% |
| DEN @ ARI | 65.7234% | 34.2766% |
| GB @ DET | 36.8495% | 63.1505% |
| LA @ LV | 62.8369% | 37.1631% |
| KC @ SEA | 48.4733% | 51.5267% |
| DAL @ PHI | 48.1582% | 51.8418% |

All 12 selected games had valid required features; none received imputed probabilities. Among all 272 scheduled REG games, 95 were excluded because kickoff had passed (94 source-completed games plus the 09:30 game), 141 were outside the earliest upcoming week selected before scoring, and 24 had unconfirmed kickoff times. Every exclusion is retained in the evidence.

Independent arithmetic rebuilt all 84 features directly from captured scores and scrimmage plays, including opponent earlier-game baselines: maximum feature and probability error **0.0**. Equivalent standardized-coordinate scoring differed by at most **1.11e-16**. All observation times precede cutoff; generation precedes kickoff; no same-day/future games or opponents’ later results enter state. Complete records reproduce byte-for-byte. Second and third runs retain the original 12 records and 2 batch/session receipts, with zero duplicates and unchanged timestamps.

**Verification:** 456 Python tests passed; the prohibited fitting test was skipped. New synthetic checks cover restricted capture hashes/seasons/URLs, cutoff boundaries, source age, non-REG exclusion before score interpretation, immutable concurrent writes, retry retention, missing inputs, leakage and disabled promotion/public writes. Existing V2 tests retain historical feature-parity and saved-coefficient verification. No frontend or production files were changed.

Immutable local records live under `data/research-v2/prospective/limited-rehearsal-2026-10-25/rehearsals/`; raw captures and receipts live under `data/research-v2/limited-rehearsal-2026-10-25/inputs/`. Both are separate from V1 and public artifacts. `python -m ml.v2_rehearsal --reproduce` verifies the retained rehearsal; it does not mint new forecasts. `python -m ml.v2_prospective` still reports disabled, and real prospective execution rejects before opening a manifest.

**Remaining activation requirements:** explicit prospective activation approval and a future start timestamp; a reviewed pre-T−60 capture path paired with actual immutable V1 forecasts; separately approved scheduling and hosted verification. This rehearsal grants none of these. No QB, injuries, weather or news enter the probabilities, no prospective accuracy was measured, and there is no model promotion recommendation.

Attribution: SportsDataverse / NFL Next Gen Stats schedule source and license retained; nflverse/nflfastR PBP under CC BY 4.0. Team margins, efficiency totals and probabilities are derived modifications. Incremental local cost $0. No production access, deployment or scheduler changes.
