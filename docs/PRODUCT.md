# Product definition — Fourth Down
Local research build: provisional Tier A. Owner: Thomas. Engineering evidence date: 2026-10-24.

## Users and scope
For an interviewer, applied ML engineer, or NFL researcher: explore historical matchups, audit model factors, compare validation metrics, and trace predictions to source data. Deliver a local React/TypeScript dashboard and an offline Python pipeline. No betting, live odds, personalized advice, paid APIs, accounts, database, autonomous research, or public release in this scope.

The demonstration uses 2023 regular-season historical replay. Every prediction is labeled retrospective. It is generated today from historical pregame features, not claimed to have been published in 2023. The daily forecast cutoff is 00:00 America/New_York on game day. Only results from strictly earlier calendar days enter features; schedule inputs are retrospectively corrected and not vintage snapshots. Probability is conditional on a non-tied outcome. The original legacy baseline previously exposed aggregate 2024–2025 metrics; this period is partially exposed. No further candidate evaluation without a frozen candidate/protocol and explicit approval.

## Acceptance
Reproduce the original 2023 model; evaluate one justified schedule-only candidate and ablations on identical observations; show actual metrics and model-generated probabilities; reconstruct each probability from its explanation; build/test all four screens; work at mobile widths and a Pages subpath; fail explicitly on unavailable or invalid data. Recurring infrastructure target $0; no deployment.

## Assumptions and unresolved decisions
The named Idea-to-Production Operating System source was not supplied or found in the inspected local materials. The assignment's Stage 0–3 artifacts, Tier A classification and G0–G3 human gates govern this build; full framework conformance remains unverified. Public data redistribution, branding, source snapshot freshness, release tier, and future live forecast cadence require owner review. Validation selection is exploratory, not an unbiased estimate of future performance.
