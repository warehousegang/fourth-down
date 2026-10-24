# Corrective release handoff — 2026-10-24

Fourth Down remains a local 2023 historical replay. The owner accepted the independent review and authorized corrective preparation only. No model was trained, tuned or changed, no additional 2024–2025 results were inspected, and no deployment, purchase, remote push or personal-site change occurred.

## Candidate and evaluation boundary
The candidate is still `schedule-v1-741cf41752`. FROZEN_MODEL.json, all eight frozen source/protocol/dependency files, the local source snapshot and forecast JSON retain their prior hashes. Its 2010–2022 preprocessing is already absorbed into the raw-scale coefficients. Features, eligibility and p >= 0.5 threshold are unchanged.

The original legacy baseline previously executed and its aggregate 2024–2025 accuracy **0.5359**, Brier **0.2492**, and log loss **0.6915** were observed. HOLDOUT_EXPOSURE.json records these owner-reported rounded values; they were not recomputed. This period is **partially exposed**, not pristine. The unchanged old manifest's unevaluated flag refers to the candidate; it does not supersede this exposure disclosure.

HOLDOUT_PROTOCOL.md and HOLDOUT_PROTOCOL_FREEZE.json were added before any further inspection. They freeze pooled and separate-season metrics, constant comparators, unchanged candidate and eligibility, paired season-week resampling (2,000 draws, seed 42; pooled draws stratified by season), and one-time reporting regardless of result. No holdout scoring or acquisition path was added. Execution requires explicit approval of the protocol, candidate and a reviewed scoring-only implementation.

## Workspace and history
The original `~/Documents/ChatGPT/AI/nfl-predictor` repository remains separate, at its initial `ccad1ae` commit with its existing untracked analysis scripts. All five originals still match the copies under legacy/ and legacy/SHA256.json. The new `~/Documents/ChatGPT/nfl predictor` workspace is the owner-selected destination, on `codex/corrective-release`. Its first commit, `cf15da8`, preserves the frozen scientific baseline; later commits record corrections and verification. New Git history establishes the current state, not the chronology of earlier model selection or exposure.

## Corrections
- Retired 32 NFL/ESPN PNGs; original CSS text team identifiers preserve the requested dark/green design. Exposure is disclosed on the dashboard.
- Included complete notices for all five frontend production packages, including transitive scheduler and Feather attribution. Preserved the complete available notices for all 41 locked Python packages. nflverse/Lee Sharpe attribution and derived-work labeling remain.
- Added the existing, unchanged 2023 demo JSON to Git, with checksum checks against the candidate and protocol. Builds reject missing/tampered artifacts or unexpected public assets.
- Pinned every official Action dependency to a verified full commit SHA. Replaced the Pages upload composite's mutable nested dependency with an explicit tar step and pinned upload-artifact. CI remains manual-only; deployment remains `.disabled`.

## Evidence and limits
Fresh checks: **22 Python passed, one retraining test deliberately skipped with fit methods blocked; 14 frontend tests; six release-packaging tests; four browser cases at root and four at /nfl-predictor/**. TypeScript/build and exact public-artifact copying pass. A fresh npm ci and build from Git archive ebdcd66 also pass without raw data or model intermediates; all production bytes match the tested workspace. Its Python suite passes 21 tests with two skips (absent raw snapshot and prohibited retraining), using the existing environment. No clean Python dependency installation is claimed. Tested browser cases have no uncaught errors, overflow or axe violations under the selected rules. Frontend/Python advisory audits report zero known vulnerabilities; Python covers all 41 locked packages without skips. This is point-in-time evidence, not exhaustive security or accessibility certification.

Independent CSV history queries and saved-coefficient scoring reproduce all 272 forecasts, 1,088 factors, cutoffs and source metadata. Candidate accuracy 0.5882352941, Brier 0.2370447317, log loss 0.6657815065; paired Brier difference -0.0099183483, week-bootstrap 95% interval [-0.0247146852, +0.0063818071]. Zero remains inside the interval. No reliable improvement claim follows. Original logistic, ablation and backtest fitted coefficients were not saved, so their historical summaries were not independently re-created under the no-fit restriction.

CORRECTIVE_VALIDATION.json records exact metrics, integrity and checks. Local logs/screenshots remain under ignored artifacts/corrective/ and artifacts/corrective-*.png. The initial subpath browser failure was a preview base-path configuration mismatch; the corrected command and successful rerun are recorded. Two upstream Zod annotation warnings remain non-blocking. Raw data and retired logos are excluded from release artifacts.

See RELEASE_GATES.md for the current recommendation and blockers; README.md for the no-fit test and local preview commands. Stop here for owner approval. Holdout execution and public deployment are separate decisions.
