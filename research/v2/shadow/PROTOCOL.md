# V2 prospective preparation — decision pending

Authority: the owner's October 25 shadow-preparation instruction, following the
existing Idea-to-Production OS v1.1 project mapping. Accepted research is `180f79f`.
This increment permits local preparation only: no protected data inspection,
fitting, activation, deployment, V1 scorecard changes or production scheduling.
`PLAN.json` records disabled status. Both approval references and start time are null.

## Exact data-use decision required

**Recommended decision for later approval:** permit acquisition of one season-isolated
2025 **schedule/score** snapshot solely to calculate each team's regular-season
`sum(scoring margin)/(completed games+4)` for future 2026 V2 predictions. Minimum
fields: stable game ID, season/type, team identities, game date/kickoff, completion
status/validation, final home/away scores. No 2025 PBP, player data, candidate
predictions, performance metrics, tuning, fitting or calibration. Never fetch 2024
or an all-season schedule. Seal raw bytes, timestamps, source metadata and checksum;
record the actual exposure date before deriving priors. Any correction is a new
version requiring review, not replacement of the sealed snapshot.

The proposed NGS file is season-isolated, not necessarily REG-only at transport:
its raw bytes may also contain 2025 preseason/postseason rows and unused metadata.
The decision must authorize retrieving/sealing that 2025-only file; parsing and
feature derivation are restricted to REG scores, with other rows excluded before
their score fields are inspected. If that acquisition scope is not acceptable,
obtain a verified server-filtered REG-only export before proceeding. Externally
computed 2025 team-margin aggregates still encode outcomes and do not bypass the
data-use decision. No combined-year download is allowed.

The frozen holdout protocol explicitly says no 2024–2025 file may be opened or
fetched during preparation. Therefore even score-only feature use requires a
**separate, append-only owner-approved amendment**, naming this scope and its
consequences. Leave `HOLDOUT_PROTOCOL.md`, `HOLDOUT_PROTOCOL_FREEZE.json`,
`HOLDOUT_EXPOSURE.json`, and their hashes untouched. The original legacy aggregate
accuracy .5359 / Brier .2492 / log loss .6915 was already exposed; this is not a
pristine holdout today. Reading 2025 scores adds outcome-level exposure and makes
2025 consumed operational feature data. A later 2024–2025 assessment must disclose
that added exposure and cannot be described as independent/pristine. This proposed
amendment does **not** authorize that assessment or alter its frozen configuration.

Completed 2025 scores precede 2026 kickoffs, so this is not inherently temporal
target leakage for a future 2026 forecast. It is still an experimental-boundary
decision. Newly collected snapshots cannot prove what was published before already
played 2026 games; no backfilled forecast can enter a prospective scorecard.

**Alternative:** retain the current prohibition. Then this exact seven-feature V2
cannot run in 2026. Do not replace 2025 with 2023, zero the prior, drop its feature,
or refit silently. A later season using authorized preceding-year data would need
its own approved scope. Data-use approval and prospective activation remain two
separate decisions; neither is granted by this preparation.

## Frozen candidate and data adapter

Candidate `v2-efficiency-ff72f16c5ea3`, model SHA256
`d4832bedb306ef315d179e5ec102e3048c2dbc7f584dd7c9803870af3b5438a6`, is pinned to
accepted result `47ba6e069a6e3ddcc4a3181017a856fd7a866f9462598d20e6a7238299265c8a`.
Base fit: 2011–2021; Platt calibration: 2022. Raw coefficients already absorb the
training-only StandardScaler. Apply the saved raw logit, then saved Platt slope and
intercept; never standardize twice, refit, recalibrate or replace the model by the
newest directory entry. Verify accepted feature-source hashes on scoring.

All seven predictors are home minus away:

| Features | Inputs and exact transformation | Availability/missingness |
|---|---|---|
| `smooth_win_diff` | Current-season wins including half-win ties; `(wins+2)/(games+4)` | Earlier dates only; verified final observed before cutoff |
| `margin_diff` | Current-season cumulative scoring margin / `(games+4)` | Missing preceding result disables affected state |
| `recent_margin_diff` | Last five margins / `(min(games,5)+2)` | Calendar-day batching; no same-day results |
| `rest_diff` | Calendar days since last completed game, capped at 14; 7 at Week 1 | Byes naturally lengthen rest; postponed/unresolved intervening game is not a bye |
| `prior_margin_diff` | Previous-season margin / `(games+4)` | Requires approved, complete 2025 score capture; no substitute-year imputation |
| `adjusted_offense_ypp_diff` | Accepted scrimmage yards/play minus 5.5, minus opponent earlier-game raw defense; sum / `(n+4)` | 2026 season-isolated PBP; missing required plays or opponent state disables probability |
| `adjusted_defense_ypp_diff` | Allowed yards/play minus 5.5, minus opponent earlier-game raw offense; sum / `(n+4)` | Positive defense rating means more yards allowed; same fixed shrinkage |

Scrimmage definition is unchanged: run/pass plays including sacks/scrambles,
excluding kneels, spikes, two-point attempts and no-play rows. Equal-game weighting,
not pooled play weighting. Both teams use pre-update opponent ratings; earlier
adjustments never use opponents' later games. Opponent earlier-date state is
reconstructed using the vintage actually captured before the **target** cutoff;
it is not a claim of original provider publication before each earlier game.
Week 1 current efficiency is legitimately zero; prior-season strength is real.

Proposed live input path, implemented offline with synthetic bytes:

1. Retain the existing SportsDataverse/NGS **2026-only** CSV outside V1 writes.
   A separately approved **2025-only** CSV supplies score-only priors. Full live
   coverage must validate 272 REG games and 17/team, with no duplicate identities;
   exceptions require investigation rather than silently dropping missing games.
2. Capture only nflverse `play_by_play_2026.parquet`, retaining exact raw bytes and
   release metadata. Validate the season column before reading football fields.
   Join PBP to the schedule on season/week/home/away/Eastern game date and validate
   canonical PBP game ID. Ambiguous, unmatched or changed joins fail closed.
3. Captures require allowlisted URLs, licensing references, SHA256, provider update
   and actual local retrieval times strictly before cutoff. Current schedule/PBP
   must have been checked within six hours of cutoff; static prior capture is
   exempt. Source-file age is reported separately: an old unchanged publication
   date is not rewritten to retrieval time and is not the sole input-validity test.
4. Build all earlier-day state, score the frozen model and seal one decision with
   source references, joins, seven values, history IDs/dates, coefficients' model
   hash, code/protocol hashes, cutoff, actual generation time and both probabilities.
   Reject generation at/after kickoff, unknown kickoff and unsupported status.
   Missing required features yield unavailable; never a neutral invented estimate.

No new network collector or workflow is activated. `ml.v2_prospective` is an offline
adapter/preparation harness; its real-data `run()` rejects **before opening input**.
Behind that gate, the manifest loader, full-coverage checks, actual generation clock,
immutable write and retry retention are implemented. An activation revision must
record both approvals and wire trusted captures and archived-V1 pairing. The simulation path requires synthetic
capture markers and fixture schedule IDs and always emits `prospective:false`.
It is not a shortcut for running real 2025 data before approval.

Manifest contract: exactly `schedule`, `pbp`, and `prior`, each with a local filename
beside the manifest and a `receipt`. Receipt fields are `kind`, `season`, `synthetic`
(false for future real captures), `url`, `license_url`, `raw_sha256`, `retrieved_at`,
and `source_updated_at`. Local filenames cannot traverse directories or be symlinks;
schedule files are bounded to 2 MB and PBP to 128 MB. The future command is
`python -m ml.v2_prospective --input-manifest PATH --game-id ID`; today it always
raises the disabled error without opening PATH. No `--enable` or clock override exists.

A read-only 2026 source audit during preparation verified nflverse asset 674570910
(updated October 25 09:03:15 UTC, retrieved 13:19:25 UTC). Its 16,551 PBP rows are
all season 2026; 94 earlier games joined to the preserved 2026 NGS schedule, producing
188 team-game totals. No prior-season data or model predictions were used. See
`current-source-audit.json`. These captures establish availability at collection
time, not before past 2026 kickoffs or an already missed T−60-minute cutoff.

## Immutable storage and lifecycle

Use only `data/research-v2/prospective/`, never `web/public`, V1 operations, model
registry or production evidence bundles. JSON decision identity binds mode, season,
game ID, scheduled kickoff and cutoff. Complete fsynced temporary files become
visible through atomic no-overwrite links. Identical retries are idempotent;
different bytes for the same decision are rejected. Concurrent writes cannot
publish partial records. Receipt SHA256 and saved probability are checked on read.
Synthetic records use a separate `simulations/` namespace; prospective writes are
also disabled. Do not infer that local hashes establish a third-party timestamp.

After later activation, an existing decision must be loaded and retained on retry,
including its original generation time. Retain unavailable attempts/reasons and
source captures. A changed kickoff creates a distinct schedule identity; retain the
old decision, mark the comparison void through a new reconciliation record and
require a new timely decision. Never rewrite the first forecast or backdate a retry.
Rollback/disable means stop shadow execution; V1 continues untouched.

## Paired prospective evaluation, declared before collection

- Start only at an explicitly approved future activation timestamp. Eligible 2026
  REG games must have a T−60-minute cutoff after activation. Previously played or
  missed games cannot be reconstructed into this cohort.
- Use that same decision cutoff for both models. Generate/archive V2 between the
  cutoff and kickoff using captures observed strictly before cutoff. The primary
  V1 comparator is the latest eligible **actual archived public V1 forecast**
  generated/archived by cutoff, with identical game/team/kickoff identity and verified
  original source/feature evidence. Do not rescore or rewrite V1. Retain its original
  timestamp, cutoff, hash, probability and source age. Ties in selection resolve by
  generation time then stable receipt hash, fixed before results are read.
- Pair only games with both valid archived predictions before kickoff. Record the
  full eligible-game denominator and V1-only, V2-only, both, neither and exclusion
  reasons **before outcomes**. Report paired coverage and forecast-age strata so
  missingness/older V1 forecasts cannot be hidden. This compares the deployed V1
  system against frozen V2; differing data ages/fitting windows mean it does not
  causally isolate the three additional features.
- Observe verified FINAL 2026 results after kickoff. Retain raw result receipt/hash
  and observation time. No protected-season result loading. Pending/canceled games
  remain unscored; ties are excluded from both binary metrics but counted. Require
  schedule identity reconciliation. Source corrections create new versioned outcome
  and evaluation receipts, never overwrite predictions or prior evaluation evidence.
- Primary: game-weighted paired Brier difference (V2−V1). Also report each model's
  Brier, log loss (machine-epsilon clipping only), accuracy at .5, ten fixed equal-width
  calibration bins including empty bins, ECE, sample counts and coverage. Report
  per-season and pooled results on identical pairs, using unrounded probabilities.
- Uncertainty: paired `(season, week)` blocks, stratified by season; sample each
  season's original number of week blocks with replacement, preserve all games and
  both predictions within blocks. NumPy `default_rng(42)`, 2,000 replicates, canonical
  season/week/game order, percentile 95% intervals with linear quantiles. Reset RNG
  per report and share draws across metrics/models. Fewer than two observed blocks:
  report point estimates/counts, not a meaningless bootstrap interval.
- 2026 is a partial-season pilot, not full-season proof. Report every completed
  predeclared cohort, including negative results. No outcome-driven stopping,
  feature selection, retuning, recalibration or automatic promotion. A full future
  prospective season and explicit owner review are required before considering
  promotion; extending this 2026 protocol to 2027 needs a recorded scope decision.

## Sources, limits, cost and OS v1.1 mapping

[nflreadpy's schedule loader](https://github.com/nflverse/nflreadpy/blob/main/src/nflreadpy/load_schedules.py)
downloads the full schedule before filtering seasons; do **not** use it across this
boundary. The season-specific PBP release supports the required narrower fetch.
[nflverse documentation](https://nflreadpy.nflverse.com/api/load_functions/) describes
explicit PBP seasons. [Updates/corrections](https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html)
can lag games and arrive through the week; no completeness or freshness SLA exists.
No EPA/CPOE, quarterback, injury, news or weather predictor is added.

Retain nflverse/nflfastR attribution and [CC BY 4.0](https://github.com/nflverse/nflverse-data/blob/main/LICENSE.md)
for PBP/derived totals; retain the existing SportsDataverse schedule attribution
and [license reference](https://github.com/sportsdataverse/sportsdataverse-data/blob/main/LICENSE).
Mark features/predictions as derived modifications. No new dependency, paid API,
server or hosted workflow; incremental preparation and expected local shadow cost $0.

G0: owner-scoped shadow preparation; G1: explicit data-use boundary, fixed model and
chronology; G2: synthetic/historical parity, provenance, reproducibility and atomic
storage tests; G3: no activation/deployment/production writes; G4: paired controlled
evaluation without automatic learning. The existing ten OS dimensions are addressed:
product/ML/functionality/engineering by this protocol and tests; AI behavior by no
LLM or invented inputs; data rights by attribution; security by URL/season/path/hash
checks; operations by disabled real ingestion and immutable storage; cost by local
free tooling; recovery by isolation and preserved original records. Historical source
vintage uncertainty, partial-season coverage, provider gaps and age-distribution
differences remain substantive limitations, not claims of production readiness.
