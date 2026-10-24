# Local operations and inactive automation

This runbook implements R05–R09 under the owner's Product Execution Directive. All commands are explicit local actions. No scheduler, remote job, public deployment, paid service or model promotion is enabled. Use Python 3.14.2 and the existing constrained environment; do not run historical acquisition or incumbent training commands.

## Collect, forecast and reconcile

From the repository root:

```sh
python -m ml.refresh
```

The command acquires only the actual current season (2026 initially), validates the source, reads retained same-season observations, scores the frozen incumbent, verifies every archived forecast against its original inputs, and writes new content-addressed forecast and operations versions. Earlier versions stay intact. `latest.json` is a replaceable pointer, never an editable historical forecast. An OS-released local lock prevents concurrent CLI refreshes. Source requests get at most two acquisition attempts (up to four HTTP calls total); rate limits, invalid schemas and other client errors are not retried. Local receipts/failures are recorded in ignored `artifacts/refresh/`.

For an offline refresh, use `python -m ml.refresh --snapshot data/current/2026/snapshot-<sha>.json`. It records the actual run time and rejects a source older than a retained newer observation. Offline mode is not a time machine: stale inputs produce unavailable forecasts, and a first final observation after a cutoff cannot prove pregame availability. The original `python -m ml.current` remains available as inference-only; the broader lifecycle command is preferred.

Computation completion is stamped explicitly; a game crossing kickoff during computation loses its probability. Source/validation/size failures occur before either latest pointer changes. Each pointer replacement is atomic, but the pair is not a cross-file transaction: an I/O failure between the writes requires a rerun. Immutable versions remain recoverable. The browser checks each file hash, model and arithmetic and fails closed if its data is inconsistent. The current artifact limit is 1 MB; operations/context/research clients use 5 MB, with an operations catalog cap of 10,000 receipts. Refresh refuses oversized outputs before updating pointers. Partitioning history into separately addressed season/game pages is required before a long-running deployment approaches these limits.

## Current context

`python -m ml.context --season 2026 --snapshot data/current/2026/snapshot-<sha>.json` explicitly captures three season-isolated nflverse assets: injury rows, timestamped QB depth-chart rows and weekly team statistics. The capture preserves raw SHA, release update and retrieval times. It is a separate context artifact with its own cutoff; it does not backfill the earlier forecast or change probabilities. Injury publication time is absent in the observed source and remains null. Absence of an injury report does not establish health; depth order does not confirm a starter. Basic efficiency joins require verified completed schedule games before the context cutoff. EPA/CPOE are excluded because their learned transformation vintages are not established. See INTELLIGENCE_DOMAINS.md and the context artifact's limitations for actual coverage.

The context command is optional and independently failing. A source failure cannot alter current forecasts. Its CLI and source budget are documented in `ml/context.py`. No weather or news collector, confirmed-starter source or LLM API is activated. These remain explicit unavailable domains, not imputed model features.

## Schedule preparation

```sh
python -m ml.refresh --plan --snapshot data/current/2026/snapshot-<sha>.json
```

The advisory plan covers at most seven days: Tuesday 09:00 Eastern, Saturday 18:00 Eastern, kickoff minus 90 minutes, and checks at kickoff plus 4/8/24 hours. Kickoff-relative times naturally include Thursday, Monday, international and unusual games. Close opportunities are coalesced within 30 minutes, with at most 32 planned runs/week and a proposed 10-minute job timeout. Postgame opportunities request status; elapsed time is never evidence of a final result. Unknown kickoffs are listed, and overdue pregame opportunities require an explicit run at actual time while kickoff is still future. Meaningful source changes can trigger an explicit refresh; no polling loop is running.

GitHub scheduled jobs can be delayed and cannot guarantee a final pregame capture. A delayed run uses actual execution/capture times, excludes already-started games and does not backdate. A missing final forecast remains missing. No automatic catch-up tuning or training occurs.

## Evidence retention and recovery

Retain `data/current/<season>/` raw source bytes and normalized snapshots, plus immutable `web/public/data/current/` and `operations/` versions. Source capture provenance is necessary to reproduce an eligible forecast; a hash alone is not proof that a missing capture contained the claimed history. [EVIDENCE_BUNDLE.md](EVIDENCE_BUNDLE.md) documents verified portable export/import. It rejects traversal, changed existing files, invalid content hashes, mixed/protected seasons and oversized archives. Latest pointers are not imported, so restoring evidence cannot silently roll back a newer pointer. Refresh after restoration to generate new pointers at actual current time. Keep the independent bundle digest with the backup; never accept a self-asserted archive manifest as authenticity.

The inactive Actions template creates a downloadable review artifact; it does not push source changes or publish a website. Durable approved retrieval of a previous runner's evidence, account-specific retention/storage policy and hosted roundtrip verification are G3 blockers. Local bundle roundtrips are implemented; hosted persistence is not claimed. The template must not be activated as a recurring service until these are resolved. Raw context captures are separate local research evidence and need their own approved retention policy before recurring context collection.

## Monitoring and investigation

`operations/latest.json` addresses a checksummed immutable evaluation. Primary metrics select one final eligible pregame forecast per game, independently of its result; all-version metrics are separate. Verified non-tied final results yield correctness, Brier, natural-log loss/surprise, baseline comparisons, probability bins and by-season counts. Ties, unknown/corrected outcomes, missing evidence and schedule changes are explicit exclusions. Corrections create a new operations version; they do not rewrite old evaluations. With no completed forecasted games, metrics are null and count zero. Existing current-season results without an original pregame forecast are not assigned invented predictions.

The deterministic investigation path emits cited schedule/result facts, testable hypotheses and demonstrated deficiencies separately. It never treats an upset as causal proof. No agent or LLM calls are made in operations. The future bounded research contract in RESEARCH_DESIGN.md permits cited explanation only and cannot change probabilities, fit/promote models or access the locked holdout.

## Controlled learning and rollback

`ml/challenger.py` is an explicit, separately versioned research entry point under CHALLENGER_PROTOCOL.md. It uses only the hash-verified preserved 2010–2023 dataset, fixed chronological folds and calibration, and never the combined loader or 2024–2025 data. Routine release tests forbid all estimator fitting; challenger experiments are deliberate separate commands. Repeating an unchanged experiment is for reproducibility, not hyperparameter search. Register every altered experiment with a new protocol/model identity before fitting. Do not retrain after an individual loss.

The actual challenger is research-only and ineligible for promotion. MODEL_REGISTRY.json keeps the frozen model operational. A later promotion needs all predeclared criteria, lawful prediction-time data, prospective shadow evidence and explicit owner approval. Rollback restores the previously approved registry/model/commit by reviewed change and reruns integration checks; immutable history keeps the model actually used for each forecast. Public rollback/redeployment is a separate approved action.

## Cost and activation limits

No new package, key, paid API, backend, database or LLM service is required. Existing local execution uses local time/storage. A conservative planning ceiling is 32 runs × 10 minutes = 320 runner minutes/week (about 1,400/month), not a benchmark or zero-cost promise. Standard public GitHub-hosted runners are free; private quotas and artifact storage depend on account/plan. Pages public projects are available on GitHub Free. See the primary references and checked date in DEPLOYMENT.md. Before activation, verify remaining allowance, disable unapproved overage, review archive growth/retention and use standard runners only. No billing settings have been inspected or changed.
