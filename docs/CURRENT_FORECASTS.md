# Current forecasting runbook

This local inference slice was authorized on 2026-10-24. It does not authorize model changes, protected-season evaluation, scheduled execution or publication. The frozen candidate is `schedule-v1-741cf41752`; raw-scale coefficients already contain its training-only scaler. No scaler is fitted or reapplied. Its four unchanged features are smoothed win-rate difference, season margin difference, recent margin difference and capped rest-day difference. Probabilities condition on non-tied outcomes. See FEATURES.md for the frozen formulas.

## Run and inspect
Use the existing Python 3.14.2 environment and unchanged requirements. From the workspace root:
```sh
python -m ml.current
cd web
npm ci --ignore-scripts
npm run dev -- --port 4175 --strictPort
```
Open http://127.0.0.1:4175/. Current Week Forecasts loads the current artifact independently. The 2023 screens retain their separate frozen JSON and descriptive validation. A current refresh performs two bounded read-only HTTP requests: release metadata and the exact current-season CSV. No provider key, trained-model download, paid API or server is needed. It writes only local observation and forecast files; errors do not advance latest.json.

On this machine the matching interpreter is `/Users/thomas/Documents/ChatGPT/AI/nfl-predictor/.venv/bin/python`. Use it read-only; do not alter or run scripts in the original repository. Do not run the legacy baseline, historical all-season acquisition, training, or holdout commands.

## Time and eligibility
- The season is the Eastern calendar year from March onward, otherwise the preceding year. Acquisition accepts only that season, and never any season before 2026. Preseason/postseason rows do not enter regular-season state.
- Each team's state resets with the season. Week 1 uses wins=0, games=0 and the unchanged smoothing priors; rest defaults to 7. No prior-season strength is used. Byes add no observations; actual elapsed days determine rest, capped at 14. Completed ties count as half a historical win, as frozen.
- The information cutoff is min(decision time, target game date at 00:00 Eastern). Only strictly earlier game dates can enter features, and each final result must have been observed strictly before the cutoff. FINAL / FINAL OVERTIME, validation flag, complete scores and known kickoff/date are required.
- Do not infer game completion from kickoff plus a guessed duration. The provider lacks a trusted end time, so first observed final is a conservative availability bound. Preserve data/current/<season>/ snapshots across runs. A first-ever refresh on game day may produce unavailable forecasts because earlier knowledge cannot be proved. Run before game-day midnight where possible; identical results in prior snapshots can establish proof. Changed scores/dates/teams cannot inherit older proof.
- The next confirmed future kickoff establishes the nominal week, but earlier unresolved schedule weeks remain visible. Older postponed/suspended games are retained with unavailable status. Confirmed games already started, final games and cancelled games are excluded. Unknown dates/times and unresolved earlier team results have explicit reasons and no probabilities.
- Reschedules retain the source game-key ID. Revised date, kickoff or nominal week changes the schedule fingerprint and forecast version. Prior local snapshots allow a schedule-change warning; a first snapshot cannot claim to know a change occurred. Scheduled international/neutral games still receive the candidate's fixed designated-home intercept; no venue adjustment is invented.
- Source age >24 hours shows a warning. No new probability is generated from a source >48 hours old. The browser suppresses estimates at min(source update +48h, generation +24h), after kickoff, or with a future generation timestamp beyond a five-minute clock tolerance. This relies on the device clock and does not guarantee source completeness. Reloading a file is not a source refresh.

## Artifacts and provenance
`data/current/<season>/raw-<SHA256>.csv` and `snapshot-<SHA256>.json` are ignored local evidence. Raw hash, source URL/asset ID, source publication time and actual retrieval time are recorded. Snapshot loading re-normalizes the raw CSV and checks exact equality. Each forecast record includes stable ID, source game ID, teams, season/week, kickoff, day, cutoff, generation time, model ID, schedule fingerprint, status/reason, four feature differences, per-team factor values, coefficients/contributions, both probabilities and prior-game observation proofs. No target outcomes are published.

`web/public/data/current/forecast-<season>-<SHA256>.json` is canonical UTF-8 JSON (sorted keys, no NaN, compact separators, final newline). `latest.json` names its exact hash and generation time; publication replaces the pointer atomically only after writing the version. Previous versions remain. The top-level model, original freeze hash, pipeline source hashes, source and snapshot hashes support an audit. Hashes establish integrity and identity, not independent authenticity of the provider. The browser verifies the content hash, exact model, cutoff ordering and every logistic/factor calculation before showing numbers.

The first real October 24 capture is retained as a regression fixture. Positive-path component tests use that immutable capture with a fixed clock so later offseason/unavailable refreshes do not break tests. Other tests validate the actual latest artifact and production fetch path. The acquisition/edge-case fixtures are explicitly synthetic 2026 schedules; they contain no protected-season outcomes.

## Exact offline reproduction
Do not fetch again for byte-level reproduction. Keep the captured raw and normalized files, the matching pipeline code and the version's as_of/generated_at timestamps. For the verified local version:
```sh
python -m ml.current \
  --snapshot data/current/2026/snapshot-8ca053cf9a54ca3f4e980ec733e89ff88ba115946a05752ef91b64a674ba202b.json \
  --as-of 2026-10-24T13:43:14.289319+00:00 \
  --generated-at 2026-10-24T13:43:14.289900+00:00
```
The exact decision timestamp must match the chosen JSON; do not guess or backdate a new acquisition. This command verifies input hashes and rewrites only the same local pointer/version. A different code hash or generation time deliberately creates a different version even when probabilities match. Without local raw evidence a clean checkout can browse and test the committed artifacts but cannot independently reconstruct the input observations.

```sh
python scripts/test_release.py
python scripts/verify_current.py
# Requires the separately retained 2010–2023 snapshot, without acquisition or fitting:
python scripts/recompute_validation.py
cd web
npm test
npm run test:release
VITE_BASE_PATH=/nfl-predictor/ npm run build
VITE_BASE_PATH=/nfl-predictor/ npm run preview -- --port 4174 --strictPort
# Separate terminal:
TEST_BASE_URL=http://127.0.0.1:4174/nfl-predictor/ npm run test:e2e
```

## Refresh design and gates
The SHA-pinned `.github/workflows/current-refresh.yml.disabled` proposes one manual job, read-only repository access, ten-minute timeout and one-day review artifact retention. There is no cron, write/push permission, deployment or enabled execution. Proposed cadence after approval: Wednesday and Saturday before game-day cutoffs, plus a manual check after schedule changes. A fresh runner has no earlier observation cache; missing proof intentionally prevents affected forecasts. Persisting approved same-season snapshot artifacts between future runs needs an explicit retention/access design before recurring activation.

Target infrastructure cost is $0 using standard public-repository runners within GitHub's applicable rules. Private-repository minutes/storage, larger runners, account configuration and artifact retention can alter that assumption; verify budgets and disable paid overage before activation. No account settings were changed and no hosted workflow ran. See RELEASE_GATES.md: local implementation is ready for review, while automation/publication and additional 2024–2025 evaluation remain separate NO-GO gates.
