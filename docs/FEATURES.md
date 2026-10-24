# Feature specification — daily-schedule-v1

All candidates use the schedule fields in DATA_SOURCES.md, restricted to 2010–2023 regular seasons. Home means designated home; neutral games are not specially modeled. Forecast cutoff is 00:00 America/New_York on game date. Only strictly earlier calendar dates update state. This avoids same-day completion assumptions; corrected historical data is not proof of vintage availability.

| Feature | Source fields / transformation (home minus away) | Missing / first-game strategy | Leakage risk and checks | 2023 ablation Brier |
|---|---|---|---|---|
| smooth_win_diff | Scores, team IDs, season, gameday; (wins + 2)/(games + 4). Tie counts half | 0.5 per team; differences 0 | Current/future/same-day scores excluded; independent filter oracle; season reset | 0.236123 without feature vs 0.237045 full; no measured incremental benefit |
| margin_diff | Same source; sum(points for − against)/(games + 4) | Zero prior; only completed games | Current outcome cannot enter predictor; oracle and perturbation tests | 0.239222 without feature; strongest incremental evidence here |
| recent_margin_diff | Same source; sum(last five margins)/(min(games,5)+2) | Zero prior with two neutral games | Chronological history; permutation invariance; no future scores | 0.237122 without feature; negligible contribution |
| rest_diff | Gameday of last completed game; min(days since,14) | Seven days with no completed season history | Derived from past dates rather than upstream rest fields; cap tested | 0.237833 without feature; small contribution |
| win_pct_diff (legacy only) | Original function: season wins/games, ties half, raw home−away | 0.5 each at opener | Original timestamp batches; independently reproduced on restricted data and parity with day batches | Original Brier 0.245306 |

No scores missing on either side contribute to history. Missing identity/date columns or invalid scores fail source validation. Missing/non-finite required forecast features produce an unavailable game, never a guessed probability. Missing kickoff or venue is explicitly labeled in UI. Season-start priors are intentional, not missing-data imputation of unknown injuries. Tests include incomplete-game behavior, ties, reset, rest cap, unsorted input, source tampering, duplicate IDs, blocked seasons, and exact explanation reconstruction.

Efficiency, opponent adjustment, venue-split performance and separate bye indicators are deferred. Play-by-play would increase acquisition and provenance complexity; venue splits reduce sample size; rest already provides schedule context. Future inclusion requires time availability and incremental evaluation evidence. Ablations diagnose the fixed candidate; they were not used for another search or post-hoc tuned model. The no-win-rate ablation is slightly better and simpler, so simplification is a documented next experiment, not a hidden improvement claim.
