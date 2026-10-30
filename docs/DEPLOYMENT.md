# Fourth Down publication and forecast refresh

Live application: https://thomashoward.dev/fourth-down/. Source and ML remain in `warehousegang/fourth-down`. The portfolio is `warehousegang/thomashowarddev`, using its existing Pages branch publisher (`main`, `/`), existing `CNAME`, and unchanged domain settings. The initial approved release was portfolio commit `6740d1150306ebd1474d4508f97b73ec1cca82d9`, from source `39b42a1bab4b72a87ea30d253b32e0528d944b04`.

## Manual verification, then separate recurring activation

The portfolio workflow `.github/workflows/fourth-down-refresh.yml` has **only `workflow_dispatch` enabled**. Its source checkout and all Actions are pinned to immutable commits. No PAT, new secret, paid service, or Pages configuration change is required. The old source-repository `portfolio-artifact.yml.disabled` remains inactive; do not enable both workflows.

The job restores immutable current-season observations and archived predictions, fetches the permitted sportsdataverse schedule/results, and uses the existing frozen model. No training, challenger promotion, or protected-season acquisition is called. Only actual completed games observed before the cutoff feed the four trained features: season win rate, season margin, recent margin, and rest. Injury/depth-chart/team-stat cards may refresh separately but never alter probabilities. A context network failure retains the previous cards with their original timestamps and expiry warnings; malformed data fails the run.

A changed source, new source revision/season, crossing kickoff, the two-hour pregame window, or a freshness deadline triggers regeneration. Otherwise the run is a no-op: no extra forecast, duplicate score, evidence ZIP rewrite, or Git commit. The source timestamp is never replaced with the polling time. Forecasts expire at the earlier of source update + 48 hours and generation + 24 hours. A stale upstream source produces unavailable forecasts, not fabricated freshness. A fresh source is renewed at 12 hours. Unknown kickoffs and postponed games receive no invented pregame times.

`.fourth-down-state/` in the portfolio's Git history retains each season's checked evidence bundle; immutable forecast/operations versions remain in `fourth-down/data/`. This is public repository data, not a private store. Jekyll excludes the dot directory from Pages. Original source-repository archives are preserved. Actions caches/download retention are not used as storage. The UI metrics still select/deduplicate eligible pregame receipts and require observed verified final scores; reruns do not inflate the prospective denominator. Existing synthetic lifecycle tests cover result reconciliation/corrections and cutoff safety.

The workflow builds in a disposable separate source checkout. ML tests forbid fitting; frontend, integrity, security, integrated routing, responsive/accessibility tests must all pass before any push. It commits only `fourth-down/` and `.fourth-down-state/` together. It refuses unrelated file changes, immutable-history changes, a moved portfolio branch, altered Pages settings, and new available forecasts within two minutes of kickoff. A normal non-force push rejects a concurrent website update. Concurrency serializes refresh runs; the last successful public site remains available while checks/builds run.

A `GITHUB_TOKEN` push does not automatically trigger Pages, so the job explicitly requests the existing branch publisher using `POST /repos/warehousegang/thomashowarddev/pages/builds` with `pages: write`. It never calls the Pages settings update API. It waits for that exact commit and verifies live receipt, data and asset hashes, plus existing portfolio content. A deployment/CDN failure is reported as a failed run. Rerunning retries publication of the same retained tree without inventing another forecast. Reference: [Pages build API](https://docs.github.com/en/rest/pages/pages#request-a-github-pages-build), [token-triggered event behavior](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow).

Run the first manual check, inspect its summary, then run again to verify idempotency:

```sh
gh workflow run fourth-down-refresh.yml --repo warehousegang/thomashowarddev --ref main
gh run list --repo warehousegang/thomashowarddev --workflow fourth-down-refresh.yml --limit 3
gh run watch RUN_ID --repo warehousegang/thomashowarddev --exit-status
```

Compare both summaries: the second should show `changed: false`, the same website commit/forecast hash and no new build request when the inputs/window are unchanged. A real source change or kickoff boundary appropriately creates another version. Check generated/source/expiry timestamps at the live application; a successful job does not guarantee the upstream feed is fresh.

**After explicit recurring-run approval only**, edit the portfolio workflow's `on` block to uncomment exactly:

```yaml
  schedule:
    - cron: '17 * * * *'
```

Commit and merge that small change to `main`. No repository setting, secret or DNS change is needed. Hourly UTC checks cover Sunday morning/international, afternoon/evening, Thursday, Monday, Saturday/holiday and rescheduled kickoffs without weekday or DST assumptions. They also poll for final results after games. Off-hour minute 17 avoids the busiest start-of-hour queue. GitHub can delay/drop scheduled jobs; this is a portfolio refresh service, not a guaranteed pregame SLA. Missed cutoffs are never backfilled. Public-repository schedules may be disabled after 60 days without activity; use a manual run/check before a demonstration or new season. [GitHub scheduling limits](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

## Local reproduction and rollback

In a clean source checkout with the pinned Python requirements and `web` npm lock installed:

```sh
python scripts/automated_refresh.py prepare --portfolio /path/to/portfolio --receipt /tmp/refresh.json
python scripts/test_release.py
(cd web && npm test && npm run test:release && npm audit --audit-level=moderate && npm run build)
python scripts/automated_refresh.py stage --portfolio /path/to/portfolio --receipt /tmp/refresh.json --archive /tmp/fourth-down.tar.gz
```

Serve the portfolio with `python -m http.server 4180 --bind 127.0.0.1 --directory /path/to/portfolio`. Run `web` Playwright with `TEST_BASE_URL=http://127.0.0.1:4180/fourth-down/`, `PORTFOLIO_URL=http://127.0.0.1:4180`, `PORTFOLIO_CHECKOUT=/path/to/portfolio`, and `TEST_ARTIFACT_DIR` set to a temporary directory. `publish_forecasts.py` is the explicit network publication step; do not call it for a local-only rehearsal. Generic packaging defaults to a fully clean source tree; its `--generated-only` option permits generated data/evidence changes while rejecting uncommitted code/model changes.

If a run fails before push, the website and its retained state are unchanged. If Pages fails after push, inspect the failing log and rerun to retry the same Git tree. Disable an activated schedule first if investigating repeated failures. To roll the displayed application back, restore only `fourth-down/` from a known-good portfolio commit and merge the checked revert. Preserve `.fourth-down-state/` and all Git history; do not erase original predictions or relabel timestamps. Before resuming refresh after a display rollback, restore the application tree matching the retained state's forecast hash (normally the last successful automation commit), or explicitly recover and validate the matching evidence pair. The job refuses a mismatched pair. A full integration rollback is a revert of squash commit `6740d1150306ebd1474d4508f97b73ec1cca82d9`; this is a separate owner-approved action.

## Cost and operational bounds

Expected additional recurring cost: **$0/month** on public repositories using standard `ubuntu-24.04` runners and existing GitHub Pages. There are no paid feeds, LLM calls, new infrastructure or retained Actions artifacts. Domain renewal is unchanged. [Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions).

Failures are visible in Actions and normal GitHub notifications; no external alerting service is installed. Source freshness and final-score availability depend on the public provider. Original code caps (5 MB operations JSON, 10,000 catalog receipts, evidence/archive size limits) fail before publication; history may need partitioning as it grows. No pruning or silent history loss is implemented. Updating model code requires a separately reviewed source pin; automation never advances that pin or learns from the protected holdout.

The aggregate static release has a bounded **100,000,000-byte** ceiling. The
previous 30,000,000-byte ceiling blocked Week 8 result publication on October 30,
2026: retained immutable versions already occupied about 29.6 MB before the next
operations snapshot. The collector had retrieved the Panthers–Packers result,
but packaging failed before a Git push or Pages build. Raising this aggregate
ceiling preserves every existing file and leaves individual JSON/parser limits,
checksums, archive path checks, the 2,000-member cap, and atomic installation
unchanged. It does not increase a browser's per-request payload or change hosting.
This provides recovery headroom, not unlimited season storage. Check retained
release growth before that ceiling is reached; a future partitioning change must
preserve archived URLs/evidence and be reviewed separately. Do not prune history
or bypass the guard to make a failed publication pass.
