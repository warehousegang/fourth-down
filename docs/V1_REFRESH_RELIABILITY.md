# V1 result refresh reliability — November 8, 2026

## Verified incident and recovery

The 15-minute Worker dispatches continued while result publication failed at the
100 MB retained static-package limit. The approved storage repair preserves every
archive and raises bounded capacity to 500 MB, with a 512 MiB expanded evidence
limit and maintenance warnings at 80%. It does not partition history.

The real 21:47:24 UTC run
[42526939374](https://github.com/warehousegang/thomashowarddev/actions/runs/42526939374)
collected Dallas–Indianapolis and Cleveland–New Orleans (overtime), published
portfolio `591945957a8dc55c09e5c385d94d63f033533d1d` at 21:57:29 UTC and
finished successfully at 21:57:44 UTC. An already-open tab updated without a
reload. The 22:02:24 UTC run
[42528177308](https://github.com/warehousegang/thomashowarddev/actions/runs/42528177308)
completed successfully with no new results and no new Pages build. These checks
do not establish a guaranteed future service level.

## Review candidate

Four secondary views loaded operations only on mount: observed schedule,
postgame analysis, forecast history and current model performance. They could
retain old states while the main cards and scoreboard updated. All four now use
the existing one-minute visible-tab polling, pause while hidden and fetch when
visible again. Selection and original forecast records remain intact. A failed
poll retains the last verified data with a compact notice and retry control;
successful polling accepts verified finals and corrections. Check timestamps
describe browser fetches, never a new upstream observation. Historical research
data and V2 code remain unchanged.

The result collector already catches transient provider network errors so safe
evidence can survive. Without a final health gate, such a run could appear
successful even though no provider check completed. The proposed workflow now
runs `scripts/check_refresh_health.py` after the existing publisher, including
no-change runs. An error or incomplete receipt fails the job; a successful query
with missing/unpublished files does not. Partial verified results may still be
published before the gate reports the outage. The gate does not make requests,
change data, retry a dispatch or send messages. Existing GitHub failed-run
notifications depend on the owner's notification preferences; email delivery
has not been independently verified.

The receipt records the actual start of restoration. The final gate reports
elapsed time through publication and warns at 12 minutes, before a run reaches
the 15-minute dispatch cadence. This complements the existing 80% storage
warning; neither warning disables integrity checks or permits overlapping jobs.

This candidate requires review and a coordinated source pin, compiled frontend
and portfolio workflow update. It does not activate another scheduler or change
the existing cron. Before merging a release, hydrate the latest production
archives again so results collected during review remain preserved.

## Regression and operational checks

- Reproduce each stale secondary view with a pending-to-final transition in an
  open tab. Check desktop/mobile layouts and accessibility after the update.
- Retain a known score through a failed fetch, accept a later verified correction,
  and preserve the original pregame probability and timestamp.
- Resume a hidden tab immediately, prevent overlapping fetches and clear timers
  on unmount. Existing lifecycle tests cover missing results, ties, postponed
  games and immutable history.
- Exercise healthy no-change collection, unavailable provider files, provider
  outage after safe publication, malformed receipts and redacted failure output.
  Keep the health gate after publication and run it even when no data changed.
- Confirm the source pin and compiled application agree, all 32 logos and
  portfolio routes work, and no model or V2 changes enter the release.

For each game-day incident, inspect the dispatch time, `results` section of the
refresh decision, publication receipt and exact Pages commit. Verify the hosted
operations hash and a real game card; a green trigger alone is insufficient.
The existing publisher validates hosted files and reports build/CDN failures.
It retries a failed Pages build on the next run without inventing another forecast.

Review receipt capacity and duration before limits are reached. At the recovery
publication, static usage was 104,342,608 / 500,000,000 bytes; the first changed
run took 10 minutes 20 seconds and the following no-change run took 6 minutes
16 seconds. Approaching the 15-minute cadence requires reviewed restoration or
partition improvements, not overlapping jobs or deleted archives. Review all
entry, archive and expanded-size caps as well as the aggregate warning. Alerts
and guardrails improve detection; they cannot eliminate provider outages or
guarantee a final score is available immediately after a game ends.
