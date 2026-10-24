# Intelligence domain inventory

The authoritative machine-readable inventory is [INTELLIGENCE_DOMAINS.json](INTELLIGENCE_DOMAINS.json). Every one of the twelve product domains records its source, license status, historical availability, prediction-time rule, transformation, missing-data policy, leakage tests and contribution status. The current operational model still uses only season win rate, cumulative and recent scoring margin, and rest. Nothing in this inventory silently expands the incumbent.

The separate schedule-intelligence challenger implements seven domains (rest/travel is partial: rest and bye features only), using ten explicitly trained features. Its per-domain ablation measurements live alongside the model and complete fold predictions in `web/public/data/research/challenger-<sha>.json`; `latest.json` resolves the version and checksum. Negative full-minus-ablated Brier favors including that group, but correlated features and observed historical seasons prevent causal or untouched-test claims. Six earlier-period-only train/calibration/diagnostic folds measure every implemented group using the fixed predeclared protocol. See [CHALLENGER_PROTOCOL.md](CHALLENGER_PROTOCOL.md).

Five required domains remain unavailable for prediction: offense/defense efficiency, quarterback availability/performance, injuries, weather, and verified developments. Travel distance is also unavailable. Timestamped eligibility controls and adversarial synthetic tests are implemented in `ml/intelligence.py`; these are ingestion boundaries, not real data collection or measured predictive contribution. They reject unconfirmed starters, stale or future observations, postgame weather, conflicting assertions and unsupported private-state news categories. The adapter has no probability-adjustment or network capability. No cost-bearing API or LLM is called.

## Primary-source findings, checked 2026-10-24

- [nflverse schedule dictionary](https://nflreadr.nflverse.com/articles/dictionary_schedules.html) and the existing immutable 2010–2023 capture support score/date-derived features. Repository [CC BY4.0 terms](https://github.com/nflverse/nflverse-data/blob/main/LICENSE.md) and nflverse/Lee Sharpe attribution are preserved. Historical publication timestamps are not proven by the extract.
- [Play-by-play documentation](https://nflreadr.nflverse.com/reference/load_pbp.html) describes history since 1999. No play-by-play has been downloaded. A future efficiency experiment needs approved per-season acquisition, timestamped eligibility, corrected-data disclosure and train-vintage control for any learned EPA transformation.
- [Injury documentation](https://nflreadr.nflverse.com/reference/load_injuries.html) describes weekly reports since 2009 and `date_modified`. That does not prove a full pregame archive or current completeness. [Depth-chart documentation](https://nflreadr.nflverse.com/reference/load_depth_charts.html) describes weekly history since 2001; a depth-chart slot does not confirm the game-day starter. Official team reports and source-specific rights still need review before ingestion.
- [Open-Meteo Single Runs](https://open-meteo.com/en/docs/single-runs-api) currently documents ECMWF runs from March 2024 and most other runs from April 2026. This cannot fill the approved 2011–2023 experiment. The stitched [Historical Forecast API](https://open-meteo.com/en/docs/historical-forecast-api) is not interchangeable with a single forecast issued before a historical cutoff. [Free API terms](https://open-meteo.com/en/terms) restrict service use to non-commercial purposes; promotional portfolio use needs assessment. No paid subscription or weather request was made.
- Official team/NFL roster, coaching and schedule announcements are candidate references. No licensed, immutable publication-vintage corpus has been captured. Public access does not establish a redistribution license. Facts must be source-backed and separately timestamped; unsupported speculation is neither a fact nor a numerical predictor.

## Current-season restriction

A 2026 prior-strength challenger would require 2025. That season remains locked; the previously disclosed legacy aggregate exposure is preserved. The challenger therefore has no operational 2026 forecast path. It does not synthesize prior strength, borrow the incumbent's probabilities and relabel them, or train on protected rows. Current 2026 forecasts continue to use the unchanged frozen model and its current-season-only source adapter.

## Concrete current-source feasibility review

A follow-up metadata-only review on 2026-10-24 found public, season-isolated current assets. This distinguishes a missing implementation from a genuinely unavailable historical training vintage. No protected-season rows were read during this review.

| Domain | Available current source | Concrete remaining work / limitation |
| --- | --- | --- |
| Injury annotations | [nflverse injuries_2026.csv](https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_2026.csv), 244,481 bytes, asset updated 2026-10-24T11:57:46Z | Capture exact bytes/SHA and receipt time, validate season and report modification timestamps, retain unknown statuses and conflicting reports, attribute repository CC BY4.0, review upstream rights before public redistribution. This can support factual current annotations; corrected report rows do not establish an earlier publication vintage for training. Missing reports must never imply healthy players. |
| Quarterback depth-chart context | [nflverse depth_charts_2026.parquet](https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_2026.parquet), 3,159,952 bytes, asset updated 2026-10-24T11:58:06Z | The [provider schedule](https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html) documents appended timestamps for the current schema. Validate those timestamps and independently observed receipts. Depth-chart slot is descriptive context, not confirmed starting availability; explicit starter confirmation requires a separate official report. No historical locked-season file is needed for current annotations. |
| Current efficiency / player performance context | [nflverse stats_team_week_2026.csv](https://github.com/nflverse/nflverse-data/releases/download/stats_team/stats_team_week_2026.csv), 77,295 bytes, asset updated 2026-10-24T13:20:49Z | Join weekly identities to games verified completed before cutoff; reject missing, ambiguous, incomplete or corrected-after-cutoff inputs. Basic yards/attempts or success-count ratios can be descriptive. Do not treat retrospective EPA generated by a model with unknown training vintage as a pregame feature. Separate challenger protocol and evaluation required for trained influence. |
| Current US weather forecast annotations | [National Weather Service API](https://www.weather.gov/documentation/services-web-api): point coordinates resolve an hourly forecast covering the next seven days; identifying User-Agent required | Verify stadium coordinates and roof applicability, capture issued/update/valid-period timestamps before cutoff and hash source bytes. US coverage does not include every international venue; unsupported locations remain unavailable. [NWS terms](https://www.weather.gov/disclaimer) permit use of public-domain products unless specifically marked otherwise, with attribution and no endorsement claims. No paid API is needed for supported venues. This current API does not supply the 2011–2023 issued-forecast archive needed for retrospective model training. |

The three nflverse adapters are now implemented in `ml/context.py` and have captured actual 2026 observations for all 13 upcoming Week 7 games (26 team sides). Weather remains a documented candidate; no weather data was acquired. These current observations do not establish past availability, affect the frozen model or complete the expanded predictive-model domains. Prior-2025 strength remains independently prohibited. Team news still needs allowlisted official sources, explicit publication timestamps, source-specific permission review and careful separation of fact from hypothesis; there is no verified uniform historical news corpus in this project.


## Implemented current context and reproduction

`ml/context.py` downloads exactly three current-season assets, each preceded by a bounded release-metadata request. Each asset has a 5 MB byte limit; depth charts also have a one-million-row and 128 MB decompression-metadata bound. No retries, paid calls, fitting or all-season downloads occur. CSV season strings are checked before football-value parsing. The depth source has no season column, so its timestamp-only column is checked against NFL season boundaries before other fields are read. The actual captured depth timestamps run from 2026-03-22 through 2026-10-24, with no protected-season rows. SHA-named raw files and receipts remain under ignored `data/current-context/2026/`; versioned public annotations and their atomic pointer are under `web/public/data/context/`. A failed refresh preserves the previous public artifact.

The actual injury CSV has **no original report publication timestamp**. It provides observed weekly designations and practice statuses; `report_published_at` remains null. Quarterback depth-chart `dt` is kept as `source_recorded_at`, explicitly a provider snapshot time, not an original official-team publication. Depth order never becomes confirmed starter status. Both sources remain contextual observations, with their own cutoff that may be later than the original forecast cutoff.

Team ratios join both teams' weekly records to the stable schedule identity, require a validated final result observed before cutoff, exclude the target and later/same-date games, and fail closed on missing or duplicate matches. Passing yards per attempt, rushing yards per attempt and completion rate are calculated for offense and opponents allowed. Exported numerator/denominator totals permit independent arithmetic checks. EPA/CPOE are not used. An independent direct CSV/Arrow check verified all 13 matchup identities, 26 team sides, player report/depth identities and all observable-stat totals and ratios; its local evidence is `artifacts/context-oracle.json`.

Fresh acquisition (six maximum requests, current season only):

```sh
python -m ml.context --season 2026 \
  --snapshot data/current/2026/snapshot-8ca053cf9a54ca3f4e980ec733e89ff88ba115946a05752ef91b64a674ba202b.json
```

Offline replay uses the same schedule and adds the preserved receipt. For byte-identical reproduction, use `as_of` and `generated_at` from the referenced public artifact:

```sh
python -m ml.context --season 2026 \
  --snapshot data/current/2026/snapshot-8ca053cf9a54ca3f4e980ec733e89ff88ba115946a05752ef91b64a674ba202b.json \
  --receipt data/current-context/2026/receipt-a7e2312c190e1242edf7fceff81c0f807e8208124bafa711a1758f1f21b25dee.json \
  --as-of '<artifact as_of>' --generated-at '<artifact generated_at>'
```

No new notice dependency is introduced: the existing nflverse/Lee Sharpe attribution remains preserved; context artifacts additionally name nflverse, link the repository and CC BY4.0, identify source SHA/timestamps and describe the derived-row/ratio modifications. Repository permission supports this local use; upstream source rights for public redistribution remain G3 review. Data cost is zero for the bounded public-source calls; availability and rate limits are not guaranteed. Historical injury/news/QB-confirmation publication vintages and historical weather issued forecasts remain unestablished, so these adapters do not justify retrospective trained contributions or model promotion.
