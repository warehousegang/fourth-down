# RC1 operational readiness

**NO-GO for hosted activation/public release.** Offline dry runs verify bounded local behavior but expose recovery work. No scheduler, Actions run or public deployment was enabled. The accepted dashboard and production pipeline are unchanged.

## Dry-run coverage and limits

`python -m ml.rc1_operations` constructs a fictitious 272-game 2026 schedule, runs the actual normalizer/generator/lifecycle/publish path in temporary directories, and produces only an ignored RC1 report. Fifteen named checks pass:

- Duplicate refresh creates the same immutable bytes; local OS lock rejects a simultaneous holder and releases afterward.
- Failure immediately before pointer replacement preserves both previous pointers. Successful replacement points at a complete checksum-valid version.
- An injected failure between current and operations publication exposes mixed generations. Rerunning the same verified input completes the second publication.
- Validating all source/model dependencies before restoring the prior pair returns the original bytes and timestamps. Later virtual review correctly finds the original expiry has elapsed; rollback does not refresh freshness.
- The synthetic bundle restores eight exact immutable files and is idempotent; corruption fails before destination creation. The separate real bundle restores nine files, with no latest pointers, and repeats with zero writes.
- A deliberately truncated immutable version fails closed and leaves the previous pointer intact. It does **not** automatically repair itself.
- Artifact budget failure occurs before either pointer changes.
- Thursday evening, Saturday, international Sunday and Monday games receive kickoff-minus-90-minute opportunities. Tuesday09:00ET and Saturday18:00ET remain the background advisory cadence. Thursday is driven by its actual kickoff, not a new Thursday cron.
- Missed pregame opportunities use actual execution time; after-kickoff opportunities are not backfilled. Existing generation-crossing-kickoff tests suppress probabilities. Eastern DST preserves local cadence hours.
- Provider outage retries stop after two attempts; HTTP429 is attempted once. Injected requests perform no network traffic.
- Workflow text checks require the reviewed explicit manual-trigger block, immutable Action SHAs, bounded permissions, ten-minute timeouts and inactive release templates. Eight adversarial tests reject extra/duplicate/flow/anchor trigger forms. This is a strict repository contract, not a general YAML validator or hosted execution test.

## Atomicity and recovery findings

`ml/current.py:publish_local` and `ml/lifecycle.py:publish_operations` each replace `latest.json` atomically after writing a version. `ml/refresh.py` validates/builds both artifacts before publication, but replaces the two pointers separately. A filesystem failure between replacements can expose different generations; the local rehearsal detects and recovers this via a same-input rerun. There is no transaction spanning both files.

Immutable version files currently use direct writes. A process or disk failure during that write can leave truncated bytes at the expected content address. A subsequent attempt rejects the collision and preserves prior pointer state, but recovery requires quarantining the corrupt file and restoring/reconstructing a verified version. The rehearsal injects an already-truncated file; it is not a power-loss durability test. A public release needs crash-safe immutable-file publication and a tested whole-snapshot commit/recovery boundary. RC1 does not silently change the pipeline or rewrite forecasts to conceal these findings.

The rehearsal's rollback is a validated temporary-directory operation. For an eventual production run: stop refresh, verify trusted model/source/bundle digests, restore immutable dependencies without overwriting divergent bytes, validate the chosen current/operations pair, then promote a coherent static package. Retain the previous approved package/receipt. Preserve all generation, observation and expiry timestamps; a stale rollback must display stale/unavailable state. Public redeployment requires separate approval. Do not use this narrative as authorization to manipulate current pointers now.

## Hosting and artifact restoration

The real `ml.evidence_bundle` export/import verifies exact2026 paths, raw-normalization identity, source observations, model arithmetic, dependencies, hashes and size limits. It rejects traversal, symlinks, mixed/protected seasons, malformed archives and conflicting existing bytes. Import is resumable for identical immutable files and deliberately does not restore pointers. Its nine-file actual roundtrip and isolated corruption scenarios pass.

The disabled refresh workflow checks that original captures exist but **does not yet restore the last successful hosted bundle**. A trusted expected digest and durable retention/retrieval mechanism are still needed. One-day uploads only deliver review artifacts. Missing caches must not become newly fabricated pregame observation times. History partitioning is also required before sustained runs reach 1 MB current, 5 MB operations or 10,000 catalog rows; current outputs fit and oversize outputs fail closed.

Only `.github/workflows/ci.yml` is active, manual-dispatch only, with contents-read permission and a ten-minute timeout. `.github/workflows/current-refresh.yml.disabled` and `pages.yml.disabled` remain inactive. The Pages template alone requests pages-write/id-token-write, with an explicit approval phrase and named environment. Actual required reviewers, repository billing and hosted environment settings have not been inspected or changed. All twelve Action references across the three files match the six reviewed full commit SHAs; those pins use Node20 and require hosted-runtime compatibility verification before activation.

The static build passes at `/` and `/nfl-predictor/`, with checksummed current/context/research/operations history, unchanged historical demo, full notices and original text identifiers. It contains no backend, secret, live provider call, paid API or simulation output. Clean source install/build and static package checksum restoration are recorded in RC1_VALIDATION.json. Local browser evidence covers desktop/mobile Chrome, deep links, error states, expired probabilities and research disclaimers.

## Rights and zero-cost assumptions

Checked primary documentation on 2026-10-24: [GitHub Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits) permits public repositories on GitHub Free, limits a published site to 1GB, and specifies 100GB/month soft bandwidth and a ten-minute deployment timeout. [Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions) says standard public hosted-runner usage is free; private allowances and storage charges depend on the account/plan. Larger runners are excluded from the $0 assumption. Account allowance, shared storage, spending limits and overage controls remain unverified. No billing settings changed.

The advisory ceiling is 32 runs × 10 minutes = 320 runner minutes/week, approximately 1,400/month; this is a limit, not a measured bill or a guarantee. Acquisition has at most two attempts; artifacts/uploads are bounded. No new dependency, credential, service or infrastructure was added. Local storage/time still has a practical cost.

[nflverse-data CC BY4.0](https://github.com/nflverse/nflverse-data/blob/main/LICENSE.md) and [SportsDataverse MIT](https://github.com/sportsdataverse/sportsdataverse-data/blob/main/LICENSE) were reconfirmed, and notices/derived-work attribution remain intact. Repository license declarations do not establish every upstream NFL redistribution right. Public-source licensing and upstream rights approval remain open, as documented in THIRD_PARTY.md. No official NFL/ESPN logo or third-party font is distributed.

## Gate to next phase

Resolve rights/license decisions, durable trusted restoration, crash-safe/coherent publication, hosted runtime/protection, account budgets, current data freshness and sustained-history limits. Reconcile remaining OS v1.1 controls and obtain owner approval for a named package/commit. Keep model promotion and holdout authorization separate. Passing this local rehearsal does not activate any workflow or approve public release.
