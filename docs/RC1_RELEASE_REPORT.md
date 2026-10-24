# Fourth Down RC1 release review — 2026-10-24

**NO-GO for public deployment or scheduled refresh. GO for owner review of the completed local RC1 preparation.** Passing tests do not approve a release. No deployment, hosted job, model fitting/promotion, holdout execution, purchase or personal-site modification occurred.

## Baseline and changes

Branch `codex/rc1-release-preparation` starts from approved commit `31213446b1eb668bf160da3ff76129e24b9bac7f`, with a clean working tree. Baseline commit `a5f700c` records 52 protected file hashes, ten local data/evidence hashes, model/version, dependency locks and the directive hash in [RC1_BASELINE.json](RC1_BASELINE.json). Implementation commit `b105134` adds offline replay, Bernoulli simulation, synthetic lifecycle scenarios and operational fault injection. Commit `0c4b43f` strengthens the workflow-trigger contract; commit `1115403` fixes a scenario-output isolation bug exposed by a checkout under `/tmp` and clarifies evidence scope. Browser tests can now save RC1 screenshots separately, preserving earlier evidence. The dashboard design and production forecasting code are unchanged.

All 52 protected files and ten data captures still match. The frozen incumbent remains `schedule-v1-741cf41752`; its preprocessing, four features, coefficients, eligibility and thresholds are unchanged. Existing forecast/context/research/operations versions and pointers are preserved. Five legacy copies still match their originals in `~/Documents/ChatGPT/AI/nfl-predictor`; that original directory supplies a read-only Python environment and was not modified or executed as a legacy pipeline. Fourth Down remains in the separate `~/Documents/ChatGPT/nfl predictor` Git workspace.

The 2024–2025 holdout is **partially exposed and locked**. The previously observed legacy aggregate accuracy 0.5359, Brier 0.2492 and log loss 0.6915 are disclosure only; RC1 did not recompute or inspect protected outcomes. The existing holdout protocol and freeze manifest are unchanged.

## Independent scientific verification

The new replay independently reconstructs each same-season feature from strictly earlier game dates and evaluates the frozen raw-coefficient equation. It does not call production feature/scoring helpers or fit a model. The 3,631-row authorized snapshot contains 3,347 non-tied training games in 2010–2022 and 272 eligible 2023 validation games. All 272 saved predictions and 1,088 factors reproduce; maximum probability difference is 2.22e−16.

| 2023 metric | Reproduced value | Descriptive 95% season-week bootstrap interval |
|---|---:|---:|
| Accuracy | 0.588235 | [0.523810, 0.653999] |
| Brier | 0.237045 | [0.220100, 0.254301] |
| Log loss | 0.665782 | [0.629217, 0.702732] |

There are 18 week blocks, 2,000 replicates and seed 42. Home-rate baseline Brier is 0.246963; paired incumbent-minus-baseline Brier interval is [−0.024715,+0.006382], crossing zero. Ten fixed calibration bins reproduce; eight are populated and their count-weighted absolute reliability gap is 0.049323. For example, the 90 predictions in the 50–60% bin average 55.31%, while the observed home-win rate is 48.89%. Full bins are retained in [RC1_VALIDATION.json](RC1_VALIDATION.json).

2023 was used for candidate selection, and the corrected historical source lacks publication vintages. This is **event-time retrospective reproduction**, not proof of complete prediction-time source availability, prospective accuracy or an untouched test. Repeated teams across weeks, one season and selection exposure limit the intervals. Fitted seasons are not presented as independent incumbent backtests. Saved challenger arithmetic and split metadata also reproduce for 1,576 predictions over 2018–2023 without refitting; this does not independently validate its fitting process. No challenger was promoted.

The independent current raw-CSV oracle verifies 13 Week 7 forecasts and 52 factors against the saved 2026 source: IDs, teams, kickoffs, daily cutoffs, feature values and coefficient arithmetic agree (maximum probability error 1.11e−16, factor error zero). Complementary pipeline replay is byte-identical, baseline checks verify the freeze, and source-proof validation covers two original captures, three forecast versions and three operations versions. These combined checks establish saved-artifact consistency and conservative observed-before-cutoff eligibility. They do not assert that the upstream schedule has remained unchanged since capture.

The unchanged current artifact is `66342f068c048d28b96b456b61d0e51d4cb981a72fce1519d53df24c383aef77`. Source update is October 23 at 11:47:43 UTC; generation is October 24 at 14:01:35.520006 UTC. At RC1 review it is over 26 hours old but not expired. **Expiry remains October 25 at 11:47:43 UTC / 07:47:43 Eastern, before Sunday kickoff.** Rereading did not reset it. Existing expiry tests hide current probabilities while preserving inspectable historical receipts. No new real source was acquired for RC1, and no forecast was replaced.

## Functional and engineering evidence

| Check | Actual result |
|---|---|
| Python release suite, fitting prohibited | 314 passed; one fitting test intentionally skipped |
| Frontend unit/integration | 88 passed |
| Packaging/integrity | 11 passed |
| Chrome desktop/mobile at `/` | 14 passed |
| Chrome desktop/mobile at `/nfl-predictor/` | 14 passed |
| Synthetic lifecycle | 14 scenarios, 322 named assertions; 31 dedicated tests |
| Bernoulli simulation | 59 dedicated tests; 0%, 50%, 80%, 100%, identical seed and ten-million-draw cases |
| Operational dry run | 15 named checks; ten dedicated tests including adverse workflow syntax |
| Security / notices | Zero known npm and Python advisories; 41 Python distributions checked; five production JS package notices verified; pip consistency passed |
| Clean source archive | 311 Python passed / four explicit raw-data-or-fit skips; 88 frontend and 11 packaging passed; subpath build byte-identical |
| Static package restoration | 22 files / 4,731,114 bytes restored exactly; package SHA256 a816c323e0c07da1311bc6826d52ed5f79591a4be19cea621b46618a9ddc5693 |
| Real portable evidence restore | Nine immutable files restored byte-for-byte into an empty temporary root; repeated import wrote zero files; no latest pointer restored |

Dedicated test counts are subsets of the Python total, not additional tests. [RC1_VALIDATION.json](RC1_VALIDATION.json) records clean-source results, exact commands/log hashes, package inventory and scope. The clean frontend installation uses the unchanged lock and offline npm cache; Python checks use the existing pinned interpreter, not a new Python environment. No hosted Linux run is claimed. Browser checks found no axe violations, horizontal overflow or uncaught page errors on the exercised routes; screenshots were inspected. This is bounded accessibility/mobile evidence, not certification across all browsers or assistive technologies.

[SIMULATION_RESULTS.md](SIMULATION_RESULTS.md) separates conditional Monte Carlo variation from software scenarios and real performance. [OPERATIONAL_READINESS.md](OPERATIONAL_READINESS.md) records atomicity/recovery limits. Automated credential-pattern scanning found no matches in candidate source/dist; finite patterns are not comprehensive secret detection. Public packaging checks reject unexpected images and tampered artifacts. No NFL/ESPN marks ship; team labels are original CSS text. Historical nflverse/Lee Sharpe attribution, current SportsDataverse attribution, complete notices and derived-work labels remain intact.

## Idea-to-Production OS v1.1 gate review

The owner's RC1 directive is the available v1.1 authority. Its ten explicit dimensions are mapped below, retaining the project's G0–G4 decisions. The full separate framework was not located in relevant local documents or the accessible Pages search. This is not a claim of complete framework certification; reconcile any additional owner-supplied controls before release.

| Dimension | Evidence / status | Remaining approval or blocker |
|---|---|---|
| Product acceptance | Owner accepted the local visuals; scope preserved; GO for local RC1 review | RC1/public acceptance remains an owner decision |
| ML correctness | Frozen arithmetic, leakage exclusions, replay, chronology and calibration reproduced | Historical publication vintages absent; selection-exposed 2023; no prospective quality evidence; holdout stays locked |
| Functional correctness | Forecast/archive/reconcile/score/investigate scenarios pass | Synthetic results cannot establish real predictive value |
| Engineering correctness | Tests, clean package, root/subpath builds, checksums and browser contracts pass | Hosted Linux/Actions runtime and environment protection unverified |
| AI behavioral correctness | Facts/hypotheses separated; late injury cannot change p; no invented causes/scores | No LLM service exercised; optional future agent remains unapproved |
| Data rights | Repository licenses and attribution checked; original team identifiers; full notices | Source-code license choice and upstream public-redistribution review unresolved |
| Security | Locked dependencies, clean advisories, finite credential scan, integrity rejection, SHA-pinned permissions | Pinned Node20 Action runtime needs hosted compatibility review; account controls not inspected |
| Operational readiness | Bounded plans/retries/locks, generation cutoff, stale states and fault tests | Two-pointer publication is not transactional; version creation not crash-atomic; hosted evidence restoration absent |
| Cost | No new service or dependency; bounded execution/artifacts; documented public-runner assumptions | Account plan, shared quotas, retention/storage budget and overage controls unverified |
| Rollback/recovery | Verified local rollback and nine-file bundle restoration preserve timestamps/history | Durable trusted bundle handoff, interrupted-write recovery and hosted rollback need implementation/rehearsal |

## Required before public release

1. Resolve the source-code license and upstream redistribution review; approve the data/notice package.
2. Implement and rehearse durable trusted source-bundle restoration/retention. One-day review artifacts are not a backup strategy.
3. Address interrupted immutable-file writes and cross-pointer consistency, or approve a tested publication transaction that fails before a mixed snapshot becomes visible. Add production recovery tooling; the isolated rehearsal alone is insufficient.
4. Verify hosted runner/Action compatibility, Pages environment protection and account quotas/budget without assuming $0 for every plan. Retain explicit human activation and publication approval.
5. Refresh real data and regenerate eligible forecasts only in a separately approved run before publication; the current snapshot expires before the upcoming games. Plan history partitioning before sustained refresh reaches client limits.
6. Reconcile any additional OS v1.1 controls and obtain owner release acceptance. ML promotion and holdout authorization remain separate decisions.

No release blocker is waived by test success. RC1 preparation stops here for review.
