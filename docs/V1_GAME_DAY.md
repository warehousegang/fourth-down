# V1 game-day experience — review handoff, 2026-10-25

Status: prepared for review. **Do not merge, publish, dispatch the proposed workflow, or activate the proposed cron without the owner's approval.** This is the boundary in the current game-day request; the earlier lifecycle-fix publication approval does not cover this increment.

## Scope and root causes

The production source is `15e956e73150ec04b1ee26abdc937553e81dbba4`, including the merged archived-lifecycle correction. This maintenance branch starts there. The independently advancing V2 branch/workflow, models, coefficients, forecast inputs, historical validation and protected holdouts are unchanged.

Three remaining issues were verified:

1. The main UI foregrounded source-age classifications and repeated warnings, obscuring the saved pick. The prior lifecycle correction already joined started games from operations; this increment reuses that join and extends archive display to canceled/postponed games with an otherwise valid original receipt.
2. The completed-score path depended on the NGS schedule release. Its 2026 file was still published at **2026-10-23 11:47:43 UTC** when checked on October 25, more than 52 hours later. Polling it hourly cannot manufacture a final result that the producer has not published.
3. Hourly polling adds up to an hour after provider publication; an already-open page also needed a reload. There was no prominent weekly/season prospective scorecard.

The previous Steelers–Saints designated forecast remains `b3e511b6096aded40a2c62638e3fb0c34a61e476ba671eb8649b80cd304c1a59`, saved **October 24, 8:22:38 PM EDT**. Its Pittsburgh probability remains **0.5467062741859874** and New Orleans **0.45329372581401256**, displayed using the existing one-decimal convention. Neither the probability nor its original timestamp is renewed after kickoff.

## Provider findings and limits

The [NGS producer](https://github.com/sportsdataverse/nfl-ngs-data) describes daily in-season production; its daily workflow is around 12:45 UTC. The [release metadata](https://api.github.com/repos/sportsdataverse/sportsdataverse-data/releases/tags/nfl_ngs_schedules) confirmed the old publication time. This establishes observed source age, **not an exact final-to-publication latency**: the source did not provide the missing final during inspection.

The additional source is the [nflverse per-game raw PBP release](https://github.com/nflverse/nflverse-pbp/releases), licensed under [CC BY 4.0](https://github.com/nflverse/nflverse-pbp/blob/master/LICENSE.md). The [official update schedule](https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html) says raw game files are usually available within 15 minutes of a game's end. This is an upstream expectation, not an SLA. The [official raw-file URL implementation](https://github.com/nflverse/nflfastR/blob/master/R/utils.R) documents the season/week/away/home naming.

Read-only sample: `2026_07_NE_CHI.rds`, SHA-256 `02e1ebdddd55ab2da4ca6795c85f5c0f5734ea9a021deaa1928343082cb4d935`, was published October 23 at **03:31:15 UTC**. Its explicit FINAL header records **CHI 30, NE 24**. The last timestamped play ended **03:22:17.237 UTC**, about **8m58s** earlier. The END_GAME row lacks a timestamp, so this is a measured publication interval from that play, not an exact final whistle measurement or a representative latency distribution. This game has no eligible V1 archived forecast in the current cohort and was **not added to prospective performance**.

The first hosted-path rehearsal made one metadata request and correctly reported Steelers–Saints as unpublished. No score was inferred from elapsed time. Real provider evidence and local synthetic tests remain separate.

The collector reads only individual current-season files for games with recorded V1 forecasts. It does not download a combined all-season schedule, access protected-season results, scrape a scoreboard website, or send outcomes into forecast features. It validates the release digest, exact season/week/team file, both teams, scheduled Eastern date, actual start, explicit final phase, integer scores and publication/observation ordering. Same-date weather delays are accepted; a changed date requires a confirmed schedule identity. Non-final files can supply a status, never an evaluation or invented live score.

Raw files and first observations are content-addressed. Repeated retrieval is a no-op. A changed file creates new evidence and a new operations version. Corrected scores replace the current evaluation once, retaining every older version and the same designated forecast. A newer schedule without a verified score cannot retract an independently verified final; a newer verified primary result or explicit cancellation takes precedence.

## Product behavior

- Upcoming: latest eligible saved pregame probability, predicted winner, original timestamp, kickoff and status.
- Started: archived pregame prediction survives a current-snapshot refresh. Unknown game status says “Awaiting result update”; it does not assert a live score.
- Final: prominent score, actual winner, predicted winner, correct/incorrect treatment, Brier and log loss, original forecast timestamp and analysis link.
- Postponed/canceled: valid prior forecasts remain visible, with a concise explanation; no evaluation. Missing input/provenance proof remains a reason to withhold a prediction.
- Prediction details: keyboard-operable native disclosure with model, cutoff, source timestamps/hash, saved feature values and missing inputs. The main page keeps one plain-language limitations note.
- Prediction Scoreboard: current-week and **current-season cumulative prospective** totals; completed eligible games, correct/incorrect, accuracy, pending, Brier, log loss and last verified result observation. One designated forecast per game. Ties, canceled/postponed games and missing eligible forecasts do not enter accuracy. With zero verified results, metrics are dashes rather than synthetic percentages. Historical validation, simulation and V2 never enter these totals.
- Visible tabs check published artifacts every 60 seconds; hidden tabs pause and refresh on return. A transient request failure retains the last verified evidence.

## Result storage and V2 compatibility

The original `forecast-evidence-2026.zip/json` interface remains a forecast/source-only archive, including its original operations generations. It excludes supplemental result files and derived result-only operations versions. This lets the existing V2 reader continue using its existing environment and exact original V1 receipts.

An additional `result-evidence-2026.zip/json` retains the complete verified evidence set when supplemental results exist. Its digest is bound in `.fourth-down-state/automation.json`. Fresh V1 runners restore both bundles before reconciling; neither bundle restores mutable latest pointers. Public operations versions carry source provenance and the original generation's hash, while raw RDS files remain outside the static site. Both bundles and public assets enter the same portfolio commit.

The frozen `requirements.txt`, `requirements-lock.txt`, original dependency notices and model manifests are unchanged. `requirements-results.txt` separately pins the pure-Python RDS reader and xarray; supplemental notices are in `RESULT_DEPENDENCY_*`. V2 jobs do not need these packages to read the compatibility archive. Outcome-specific tests skip at collection only when this separate dependency set is absent; the V1 release suite installs it and runs those tests.

## Refresh proposal and cost

The existing Worker remains active with its existing hourly configuration until separately approved. The proposed Worker config in this branch is **disabled, with no cron triggers**.

After approval, replace the same V1 Worker's cron with `2,17,32,47 * * * *`. A small public `data/game-day.json` hint contains only schedule IDs, kickoffs and statuses:

- From 15 minutes before a confirmed kickoff until verified completion, cancellation or postponement, check every 15 minutes.
- High-frequency checks are bounded at kickoff +24 hours. Unresolved games then continue hourly. A bad, missing, stale (>7 days) or oversized hint falls back to hourly.
- Outside active windows, dispatch only at minute 17. The Worker checks unfinished/recent GitHub runs and sends at most one POST; ambiguous failures are never retried. Existing GitHub concurrency remains unchanged.
- Every refresh checks metadata once, downloading at most 16 changed current-season game files (17 provider requests maximum per run). Missing files and network outages retain prior outcomes.
- Unchanged data performs no frontend build. Score-only updates reuse the previously verified compiled assets at the same source commit, updating operations/hint/evidence and running Python, static integrity and publication checks. Source or forecast changes require the complete frontend/browser build.

Expected latency **after provider publication** is 0–15 minutes polling + GitHub startup/queue/checks/Pages propagation + at most one minute in an open visible tab. **15–30 minutes is the normal-operation target, not a measured production guarantee.** A 20-minute job timeout, queue delays, provider failures or Pages delays can exceed it. After the 24-hour window, the deliberate low-cost fallback is hourly. Separately, upstream raw-file publication may itself take ~15 minutes after game end.

Expected additional recurring cost: **$0**. Both repositories are public and use standard hosted runners; [GitHub documents these as free](https://docs.github.com/en/billing/concepts/product-billing/github-actions). This proposal uses the existing Pages site and V1 Worker: 96 cron invocations/day maximum, one public hint request each, up to two additional GitHub subrequests per dispatched invocation, one cron expression and no storage/database/LLM/paid API. [Workers Free limits](https://developers.cloudflare.com/workers/platform/limits/) include 100,000 requests/day, 50 subrequests and 10ms CPU per cron invocation. The compact hint is capped at 64KB/300 games. Network wait is not CPU time. Actual new Worker CPU and queue latency still require the approved hosted rehearsal; do not silently upgrade a plan.

## Verification

The local release evidence includes:

- Python no-fit suite, including current-season acquisition, immutable duplicate/correction evidence, raw replay, final/tie/cancellation rules, outages, archive roundtrip/tampering, no-inference score-only preparation and compiled-asset reuse.
- Frontend arithmetic/provenance checks, zero/partial/weekly/season scoreboards, disclosure presentation and visible-tab polling/outage recovery.
- Shared Python/TypeScript forecast-selection vectors, including postponed/canceled archives with invalid input proof still rejected.
- Release checks for frozen coefficients, historical/research artifacts, original Action pins, data checksums, local assets and the new schedule hint.
- Scheduler tests with fake HTTP only: disabled config, windows, hourly fallback, malformed hints, busy/duplicate suppression, single POST and sanitized failures.
- Chrome desktop/mobile lifecycle, automatic final/correction updates without reload, outage retention, all 32 logos, keyboard/axe checks and original portfolio routes/assets. Synthetic final scores exist only in controlled test routes.
- npm advisory scan and a separate advisory scan of the two added Python packages.

| Local check | Result |
|---|---|
| Python, fitting disabled | 397 passed; 4 explicit unavailable historical-snapshot skips |
| Frontend unit/integration | 176 passed |
| Release/package checks | 11 passed |
| Offline scheduler | 8 passed |
| Chrome desktop/mobile, integrated portfolio | 54 passed |
| Dependency advisories | 0 npm; 0 in the two added Python packages |
| Protected baseline | 45 model/protocol/dependency/historical/logo files identical; original PIT–NO designation, probabilities and timestamp identical |

See the accompanying validation receipt for package/source hashes and log hashes. No new production/Cloudflare run or deployment is claimed.

## Publication after approval

Use the reviewed maintenance commit and the existing publisher. Keep V2's source/ledger/schedule untouched. The local review uses `source` and `portfolio` below as sibling disposable checkouts; resolve both to the approved revisions first.

1. Approve and merge the source correction. Record the exact reviewed V1 source SHA. Fetch the latest portfolio main immediately before preparing the publication; an older preview must not replace newer retained evidence. Hydrate from that portfolio, then run the production preparation:

   ```sh
   python -m pip install -r requirements.txt -r requirements-results.txt -c requirements-lock.txt
   python scripts/automated_refresh.py prepare --portfolio ../portfolio --receipt /tmp/fourth-down-game-day-refresh.json
   python scripts/test_release.py
   node --test ops/external-scheduler/dispatch.test.mjs
   cd web
   npm ci --ignore-scripts
   npm test
   npm run test:release
   npm audit --audit-level=moderate
   VITE_BASE_PATH=/fourth-down/ npm run build
   cd ..
   python scripts/automated_refresh.py stage --portfolio ../portfolio --receipt /tmp/fourth-down-game-day-refresh.json --archive /tmp/fourth-down-game-day.tar.gz
   ```

2. Render `ops/external-scheduler/fourth-down-refresh.yml.proposed` into the portfolio's existing `.github/workflows/fourth-down-refresh.yml`, replacing its single source placeholder with that exact 40-character SHA. Confirm it equals `fourth-down/release.json.source_commit`. Keep the workflow manual-only and the existing concurrency/Pages publisher. The staged app, both state bundles when present, automation receipt and source pin must be one reviewed portfolio commit.
3. Serve that portfolio locally and run the full browser suite with `TEST_BASE_URL=http://127.0.0.1:4180/fourth-down/`, `PORTFOLIO_URL=http://127.0.0.1:4180` and `PORTFOLIO_CHECKOUT` pointing to it. Confirm the original Steelers–Saints probabilities/time/designation, frozen/history/logo checksums, and no changes to portfolio files outside the application, retained state and that workflow.
4. After publication approval, merge the portfolio change through the existing ThomasHoward.dev workflow. If main has advanced, rebuild/restage from its newest retained state first. Verify the existing Pages build succeeds, then compare live `release.json` and every listed file hash with the reviewed tree. Check game cards, scoreboard, analysis/history routes and the portfolio entry points.
5. Make one approved manual refresh run with the updated portfolio workflow, inspect its provider/provenance receipt and confirm idempotency on unchanged data. The existing hourly Worker may continue at this stage; this does **not** activate the faster cadence.

## Separate schedule activation after approval

Use the same `fourth-down-scheduler` Worker and existing encrypted `GITHUB_TOKEN` binding. No public HTTP handler, new credential, extra worker or paid plan is needed. The previously reviewed deployment tooling is `wrangler@4.152.0`.

1. Verify the new live scheduling hint, source pin, result path and manual refresh before enabling the new cron. Inspect current V1 configuration/version and retain it for rollback. Do not alter the separate V2 worker.
2. During an actual active game window (or the hourly minute-17 slot), use the disabled candidate for one approved remote scheduled preview:

   ```sh
   cd ops/external-scheduler
   WRANGLER_SEND_METRICS=false npx --yes wrangler@4.152.0 dev --remote --test-scheduled --var ENABLED:true --ip 127.0.0.1 --port 8791 --show-interactive-dev-session=false
   ```

   Send exactly one event to `http://127.0.0.1:8791/__scheduled?cron=2%2C17%2C32%2C47%20*%20*%20*%20*`. Inspect the sanitized receipt, corresponding GitHub run and Cloudflare CPU/subrequest usage. Stop the preview. A duplicate/busy skip is expected if the existing hourly Worker already dispatched; never force a second dispatch around it.
3. Only after a successful approved rehearsal, set `vars.ENABLED` to `"true"` and `triggers.crons` to `["2,17,32,47 * * * *"]` in the deployment config. Deploy to the existing Worker:

   ```sh
   WRANGLER_SEND_METRICS=false npx --yes wrangler@4.152.0 deploy --config wrangler.json
   ```

4. Confirm exactly that trigger, native GitHub cron still absent, no V2 configuration changes, and one successful scheduled refresh with no overlapping run. Allow Cloudflare cron propagation. Measure provider publication → capture → Pages → visible result using saved timestamps. Do not promise the latency target before this observation.

Rollback scheduling by redeploying the retained prior hourly V1 Worker/version and cron `17 * * * *`; do not add a parallel cron. To stop dispatch, deploy `ENABLED=false` with an explicit empty cron array. For UI/result-reader rollback, restore a previously reviewed source pin and compiled assets **together**, retaining all newly published immutable forecast/result/evidence files. Never revert the whole portfolio tree over newer history, rewrite original forecasts, or retrain as recovery.

## Remaining limits and proportional OS v1.1 mapping

Owner approval, the controlled hosted Worker test, and measured post-publication production latency remain release gates. A missing provider file remains pending; no source offers a final-publication guarantee. Multi-season cumulative performance is outside this current-season increment. The fully separate OS document was not available in the existing project record; this uses the ten dimensions already mapped in RC1 and makes no broader certification claim.

| Dimension | Evidence / boundary |
|---|---|
| Product acceptance | Clear saved picks, completed cards and prospective scoreboard; owner review pending |
| ML correctness | Frozen model/inputs unchanged; original receipts/designation preserved; no fit/holdout execution |
| Functional correctness | Upcoming/live/final/delayed/canceled/tie/correction and outage scenarios |
| Engineering correctness | Python/frontend/release/browser tests; isolated build and retained-state checks |
| AI behavioral correctness | No generated scores, live-probability claims, synthetic performance or causal claims |
| Data rights | Published CC BY 4.0 game files, attribution and pinned dependency notices |
| Security | Bounded parser/network/assets, hashes, URL allowlists, unchanged secret handling and Action pins |
| Operational readiness | Idempotency, correction evidence, legacy V2-compatible archive, concurrency and rollback |
| Cost and scalability | $0 target, bounded requests/windows/files, no-change and outcome-only build paths |
| Release governance | Source/app pin together; no merge/deploy/cadence activation in this request |
