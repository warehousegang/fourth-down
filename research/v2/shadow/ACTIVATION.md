# V2 controlled shadow activation

Owner-approved start: **2026-10-29T00:00:00Z** (October 28, 8:00 PM EDT).
Authorized on October 25, 2026 in `AUTHORIZATION-2026-10-25.json`. The hosted
workflow gate is enabled for commissioning; the future cohort boundary remains
fixed. The separate Worker stays disabled until its scoped credential is installed
and external dispatch is verified. The accepted rehearsal, its PLAN/PROTOCOL, prior
amendments, and seven-feature fitted model are unchanged.

Each evaluation cutoff is kickoff minus 60 minutes and must be strictly after
the activation boundary. Stage complete, hash-verified 2026 schedule/PBP and
actual V1 archive bytes during T−90 through strictly before T−60. Reuse only the
already authorized 2025 score-source SHA; reject a changed prior vintage before
download. No 2024 source, new fitting, calibration, selection or retrospective
evaluation is authorized.

At T−60 through T−45 inclusive, use the latest sealed stage whose separate Git
commit also predates T−60. A late-persisted stage is ineligible. Preserve
actual generation time and report finalization delay; the 15-minute grace is
queue tolerance, **not permission to use later information**. Recheck schedule
identity at finalization; later schedule bytes may validate identity only, never
enter features. No stage, missing inputs/provenance, unconfirmed kickoff, missed
window, outage or schedule change means an explicit exclusion, never backfill.
Free infrastructure cannot guarantee execution at an exact second.

Pair against the most recent eligible **actual V1 forecast observed in the final
pre-cutoff stage**, ordered by original generation time then artifact hash. Keep
its probability, original timestamp, feature cutoff, original source proof,
Git commit and observed archive receipt. Both models share the evaluation cutoff;
the older V1 generation/feature cutoff is not misrepresented as T−60 generation.
A V1 forecast not observed before cutoff cannot enter the pair. Unchanged source
publication age does not rewrite forecast age or manufacture freshness.

Separate ledger: content-addressed source blobs, stage receipts, exclusive
per-game/kickoff decision slots, append-only schedule-change voids and coverage
receipts. A schedule revision creates a new identity; old decisions stay intact
but are excluded through void receipts. Coverage lists every regular-season
schedule row, pre-activation/not-yet-due/unconfirmed/missed states, both/V1-only/
V2-only/neither categories and reasons. Rehearsals, synthetic tests and hosted
ad hoc dry runs always have `prospective=false`, `scorecard_eligible=false`.
No inference receipt alone proves successful durable capture: the separate Git
ledger commit must also be retained. Recovery must never regenerate a missed
forecast or alter a timestamp.

Paired evaluation remains the existing frozen future protocol: Brier difference
V2 minus actual V1 is primary; log loss, accuracy at 0.5, fixed calibration bins,
per-week/coverage and V1-age strata secondary. Exclude ties from binary metrics,
report them separately. Resample season-week blocks (2,000, seed 42); fewer than
two blocks means no interval. Compare only both-model, unvoided, post-activation
records committed before kickoff. No automated promotion or outcome scoring is
performed by this preparation.

## Activation sequence

1. The owner approved this start and T−60 input / up-to-15-minute finalization
   policy on October 25. Never backdate captures or substitute a rehearsal.
2. A separate public `v2-shadow-state` branch has been initialized at `78ce52f`,
   with deletion/force-push protection and linear history;
   no application files, Pages integration or V1 state. Git fast-forward pushes
   reject stale writers; additions only, no force pushes. Protect against deletion.
3. Integrate only reviewed V2 files and the manual capture workflow template
   `ops/v2-shadow/workflow.yml.disabled` as `.github/workflows/v2-shadow.yml`.
   Record approval in ACTIVATION.json and enable its gate. Public V1 source pin,
   website, hourly scheduler and model stay unchanged.
4. The approved separate Free Worker `fourth-down-v2-shadow-prepared` is deployed.
   Its commissioning config has `ENABLED=false`, no cron, no route. Create a fine-grained token for Actions
   read/write on `warehousegang/fourth-down` only; store only as encrypted
   `GITHUB_TOKEN`. Do not reuse or alter the public V1 scheduler/token.
5. After verifying a manual tick and durable ledger commit, enable the Worker
   with `*/5 * * * *`. It checks the 2026 calendar each tick, dispatching only in
   T−90..T−45 windows plus one daily 11:00 UTC coverage/recovery sweep. No weekday
   assumptions: Thursday, Sunday, Monday, international, odd-minute and DST
   kickoffs use UTC event times. Workflow concurrency does not cancel captures.
6. Observe the first actual T−60 capture, pre-kickoff Git receipt and subsequent
   duplicate tick before trusting prospective coverage. Hosted dry-run success
   is not evidence of unattended timing. Do not report unattended capture as verified until that scheduled run succeeds.

Operational controls: set Worker ENABLED=false/remove its cron to stop dispatch;
set ACTIVATION.enabled=false to stop acquisition even if a dispatch is queued.
Rotate/revoke its scoped token in GitHub and replace only its encrypted secret.
Worker non-204/calendar errors and failed Actions runs require investigation.
A failed fast-forward push retains a recovery artifact (seven days); compare
hashes against the remote ledger before retrying original bytes. Never rewrite
missed captures. Monitor coverage and source publication/retrieval ages, not
just green runs. Inspect final-score provenance and voids before any later
paired reconciliation. Public Actions and the Workers Free plan target $0;
no paid resources are required or authorized.

Cost references checked October 25, 2026: [standard runners for public repositories](https://docs.github.com/en/actions/concepts/billing-and-usage)
and [Workers Free limits](https://developers.cloudflare.com/workers/platform/limits/).
The proposed 288 lightweight calendar checks/day are below the shared 100,000
request/day allowance; verify the account's remaining trigger quota and CPU
usage when deployment is approved. No paid plan is required by the design.
