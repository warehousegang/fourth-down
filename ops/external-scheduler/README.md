# Fourth Down external scheduler

Activated with owner approval on October 24, 2026, at 9:35 PM Eastern
(2026-10-25 01:35 UTC), on **Cloudflare Workers Free**.

- Worker: `fourth-down-scheduler`; active version
  `3f4176e8-6c0b-4581-a9d1-083578303fc0`.
- One hourly trigger: `17 * * * *` UTC; `ENABLED=true`.
- No HTTP endpoint, public route, database, DNS change, or runtime dependency.
- `GITHUB_TOKEN` confirmed as `secret_text` by name only, including after deployment.
  The owner entered the fine-grained PAT directly into Cloudflare. Its value was
  never read, printed, or stored in this repository.
- [Portfolio PR #6](https://github.com/warehousegang/thomashowarddev/pull/6) merged
  as `9c27895f8bd2ac15f7c70c91341b5568332f2e0e`, deleting only the two native cron
  lines. Manual dispatch, concurrency and publication safeguards remain active.
- Forecast source pin remains `d0f4a763d96bc418df489877617363b4e4acb2b6`.
- First unattended production invocation is **pending**. Next scheduled slot:
  October 24, 10:17 PM Eastern / October 25, 02:17 UTC. Activation is not proof of
  delivery. Cron configuration can take up to 15 minutes to propagate.

## Verification

With production still disabled and its cron list empty, Wrangler's **remote**
preview executed the prepared handler on Cloudflare using the existing encrypted
secret. At `2026-10-25T01:33:55.162Z`, it dispatched
[run 40151125951](https://github.com/warehousegang/thomashowarddev/actions/runs/40151125951).
The GitHub run completed **successfully**, checked current source data, restored
retained evidence, and verified live publication. It recorded `changed=false`,
`reasons=[]`, and `pages_build_requested=false`. Original generation and source
update timestamps were retained. This was a hosted one-off preview test, not an
unattended production cron event. The preview process is stopped.

Repeated hosted calls returned `skipped_busy` and then `skipped_existing`, creating
no additional run. The initial hosted attempt exposed a Workers compatibility
issue: `redirect: 'error'` is unsupported. It failed before dispatch. The only
runtime correction uses `redirect: 'manual'`; existing status checks reject every
3xx response without following it. No retry or credential logging was added.

Verification: 25 scheduler tests and 32 existing refresh tests passed, with no
fitting or protected holdout evaluation. All 106 live app/portfolio assets matched
production bytes; all 32 logo PNGs and seven forecast/history versions remain.
The portfolio merge changed only the workflow; 113 other tracked files were
byte-identical. The merge may trigger the site's normal Pages build even though
website bytes did not change. Local evidence: `artifacts/external-scheduler/`.

## Operation and cost

Cloudflare calls GitHub's existing `fourth-down-refresh.yml` dispatch endpoint on
`main`. GitHub retains responsibility for acquisition, frozen-model inference,
immutable archives, outcome reconciliation, tests and atomic publication.

Expected recurring cost: **$0**, using Workers Free and standard Ubuntu runners
in the public GitHub repository. One cron runs about 24 times/day, at most 744/month,
with normally two GitHub requests per invocation. Monitor Workers & Pages → account
usage and this Worker's Metrics; confirm the plan remains Free. Monitor GitHub
Actions usage/billing as well. Do not upgrade or attach paid resources. Production
cron CPU/limit behavior still needs the first unattended invocation; preview
execution alone does not prove production resource-limit behavior.

The Worker suppresses dispatch when any recent run is unfinished or a run already
exists in the current `:17`-to-`:17` interval. Failed runs also count for that slot.
There is one POST attempt, no automatic retry, and `controller.noRetry()` is set.
The history check is not an atomic lock; GitHub's unchanged `fourth-down-refresh`
concurrency group prevents overlapping refresh jobs, and retained-state
idempotency prevents duplicate publication. This does not promise exactly-once
execution or a scheduler uptime guarantee.

## Verify each execution and detect failure

1. In Cloudflare → Worker → Observability / Cron Events, find the scheduled event,
   its timestamp, outcome and sanitized `run_id`. Cron Events may take up to 30
   minutes to appear. A dispatch success alone is insufficient.
2. Open the matching [GitHub Actions run](https://github.com/warehousegang/thomashowarddev/actions/workflows/fourth-down-refresh.yml).
   Require `workflow_dispatch`, branch `main`, and `conclusion=success`. Inspect
   the refresh decision and final publication receipt. A no-change run is valid.
3. Compare the live `fourth-down/data/current/latest.json` pointer and its SHA-256
   with the referenced forecast. Inspect `source.source_updated_at`, `generated_at`
   and `valid_until`; a successful scheduler check must not renew stale source data.
4. For postgame scoring, inspect the operations artifact referenced by
   `fourth-down/data/operations/latest.json`: `games`, `metrics`, `warnings`, and
   source timestamps. Require a completed source result reconciled to an eligible
   pregame archive. Pending/unscored games are not prospective accuracy evidence.
   The retained `.fourth-down-state/forecast-evidence-2026.zip` and receipt must
   match their SHA-256; previous immutable forecast/history files must remain.

Enable GitHub Actions failure notifications for the token owner if desired. They
cover runs **after** dispatch. Dispatch failures appear in Cloudflare logs: 401
usually means expiry/revocation; 403 permissions/rate limits; 404 repo/workflow
access; 422 ref/dispatch configuration. Never log headers, secret values, or raw
response bodies. No run for two hourly windows requires checking Cloudflare events,
`ENABLED`, token expiry and GitHub workflow status. There is no separate dead-man
alert service; GitHub cannot notify about a dispatch it never received.

For a failed GitHub job, inspect its failed step and rerun the existing workflow
from GitHub. Preserve retained state and source pin. Publication aborts if remote
`main` moves or checks fail. A failed Pages build can be retried from the same
retained tree. Check run history before retrying an ambiguous dispatch timeout.
Do not regenerate old predictions or retrain to recover a scheduler failure.

## Disable and rotate

To disable: set `vars.ENABLED` to `"false"` and `triggers.crons` to `[]` in
`wrangler.json`, then run from this directory:

```sh
WRANGLER_SEND_METRICS=false npx --yes wrangler@4.152.0 deploy --config wrangler.json
```

Confirm no triggers remain. Do not omit `triggers`, which can preserve a cron.
Allow propagation and an already accepted GitHub run to finish. For an immediate
hard stop, revoke the PAT in GitHub; that does not cancel an already running job.
Manual GitHub dispatch remains available. Restore native cron only after Cloudflare
is disabled, by reverting PR #6. No forecast-history rollback is needed.

Rotate before the PAT's actual GitHub expiry (90 days was recommended; inspect the
owner's token settings for the selected date). Create a new fine-grained PAT for
**only `warehousegang/thomashowarddev`**, **Actions: read/write**, and implicit
**Metadata: read**. Enter it directly into Cloudflare's existing `GITHUB_TOKEN`
secret and deploy; observe a successful dispatch before revoking the old PAT.
For suspected compromise, revoke first. Never paste credentials in chat or files.
Verify presence with `wrangler secret list`, which returns names/types only.

## Reproduce the controlled test

Keep production disabled with `crons=[]`. Use the existing encrypted binding:

```sh
WRANGLER_SEND_METRICS=false npx --yes wrangler@4.152.0 dev --remote --test-scheduled --var ENABLED:true --ip 127.0.0.1 --port 8791 --show-interactive-dev-session=false
```

In another terminal, send exactly one event:

```sh
curl --fail-with-body 'http://127.0.0.1:8791/__scheduled?cron=17%20*%20*%20*%20*'
```

Read the sanitized remote receipt, wait for that exact GitHub run to succeed,
verify retained/live artifacts, then stop Wrangler. This localhost endpoint is a
proxy to Cloudflare's hosted preview, not local model execution. It uses no local
PAT. Only after success, restore the approved active config and deploy. Do not
add an HTTP handler, public route or another scheduler for testing.

Local regression checks: `node --test worker.test.mjs` and the existing Python
`tests/test_automated_refresh.py tests/test_refresh.py` suites. The configuration
test intentionally asserts the approved active state; adjust that expectation if
intentionally checking in a disabled configuration.

References: [Cron Triggers](https://developers.cloudflare.com/workers/configuration/cron-triggers/),
[Workers runtime redirect implementation](https://github.com/cloudflare/workerd/blob/main/src/workerd/api/http.c%2B%2B),
[Worker secrets](https://developers.cloudflare.com/workers/configuration/secrets/),
[minimum dispatch permission](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event),
[Workers pricing](https://developers.cloudflare.com/workers/platform/pricing/),
[GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions).
