# PRD — Fourth Down current NFL forecasting

Revision 2, 2026-10-24. Material scope change authorized by Thomas: locally runnable upcoming current-week forecasts alongside the unchanged 2023 retrospective analysis. Governed by the supplied Idea-to-Production Stage 0–3 artifacts and G0–G3 human gates. Local research remains provisional Tier A; public/automated operation requires reassessment. The separate full OS source remains unavailable, so no broader framework conformance is claimed.

## Product and users
An interviewer or NFL researcher can open Current Week Forecasts, see upcoming matchups and model probabilities, inspect every input/contribution, and distinguish forecast generation, observation and kickoff times. Historical analysis retains its own route and validation evidence. The current-season score is an application of the frozen model, not a new evaluation or model-selection experiment.

## Scope and forecast timing
Retrieve only a documented current-season schedule asset (initial supported season: 2026), including final results, from SportsDataverse's per-season NFL Next Gen Stats schedule release. Do not retrieve the combined nflverse schedule or any 2024–2025 data. Preserve nflverse attribution on historical analysis. Persist checksummed snapshots locally, normalize a narrow field whitelist, and publish versioned static JSON locally.

Each forecast uses only this season's final results with scheduled game dates strictly earlier than the target date and confirmed observed-final evidence before its information cutoff. The cutoff is the earlier of the decision time and 00:00 America/New_York on the target game date. A first observation after that cutoff cannot prove earlier availability: mark affected predictions unavailable. Do not infer a completion timestamp from kickoff. New snapshots can establish conservative observed-final bounds for later forecasts. Future and same-day scores never enter state. The previous season, injuries, player news, weather, market odds and new strength estimates are excluded.

Reuse the frozen Record.values formulas and score function without modifying their files, coefficients, absorbed training scaler, feature order, season reset, tie handling, rest cap or decision threshold. Week 1 uses the frozen priors. Byes create no games; rest uses actual elapsed calendar days. A changed kickoff/date requires a newly versioned forecast. Unknown dates/times and postponed games have no guessed probability. Missing or unconfirmed historical results fail closed for affected teams.

## Acceptance criteria
- AC1: One explicit command fetches only the allowed current-season asset, records URL/retrieval/source-update/checksums, and creates forecasts without training or touching the 2024–2025 protocol.
- AC2: All source rows are season-checked before result normalization. Production coverage, identity, unique matchup IDs, team aliases, dates, scores and statuses are validated. Schema/coverage failures never promote a new artifact.
- AC3: Leakage tests perturb future/same-day results, incomplete statuses and observations after cutoff; earlier forecasts stay unchanged or become explicitly unavailable. Independent parity tests reproduce the frozen feature definitions.
- AC4: Week 1, byes, reschedules, postponements, missing outcomes, missing/unconfirmed kickoffs and season boundaries have explicit deterministic behavior and warnings.
- AC5: Every available forecast carries stable matchup ID, source game ID, kickoff, cutoff, generation time, snapshot/model/code lineage, per-team feature values, contributions and both probabilities. Same inputs/timestamps produce identical bytes. Changed input creates a new version; old versions remain.
- AC6: Current Week Forecasts is the default screen. It loads independently of historical data, displays freshness and missing-data/model warnings, and validates probabilities against the unchanged frozen coefficients before rendering. Past-kickoff and expired snapshots cannot masquerade as upcoming forecasts.
- AC7: Existing historical UI/ML tests, current-flow tests, production-subpath checks and immutable artifact checks pass. No holdout evaluation, fitting, deployment, purchases or personal-site edits occur.
- AC8: A disabled, SHA-pinned Actions refresh design is bounded, writes only a downloadable candidate artifact, and has no schedule, push, publication or deployment permission.

## Non-goals and success measures
No retraining, tuning, automatic evaluation, paid data, persistent backend, roster/news enrichment, betting advice or automatic publication. Target recurring infrastructure cost remains $0 subject to GitHub account limits. Success means verified artifact lineage and all eligible upcoming games either scored or accompanied by a specific unavailability reason, with no invented data or performance claims. Timely refresh is a manual responsibility in this slice; source freshness is visible, not guaranteed.
