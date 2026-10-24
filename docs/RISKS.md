# Risks and owners
| Risk | Mitigation | Owner |
|---|---|---|
| Holdout contamination | Partial exposure already occurred in the legacy baseline; disclose it, preserve guards, freeze prospective protocol, require approval before any further assessment | ML maintainer |
| Retrospective data corrections | Snapshot/hash + historical replay label; no vintage-data claim | ML maintainer |
| Validation selection / weak gain | Publish all baselines, uncertainty, ablations; do not call the partially exposed period pristine | ML maintainer |
| Missing roster/QB/injury context | Explicit limitations; research separate from probabilities | Product owner |
| Licensing/trademark ambiguity | Attribution and full dependency notices; official logos removed; upstream/source-license G3 review remains | Thomas |
| Incomplete OS framework source | Follow provided gates; request full framework before public release | Thomas |
| Dependency supply chain | Pin lockfiles, audit, manual CI, no secrets or pickle | Engineering |
| Cost or accidental deployment | No scheduled public workflows or deployment until approval; explicit local collection/evaluation is authorized | Thomas |
| Runtime/platform drift | Python 3.14 actual tests and recorded versions; clean frontend archive build checked; cross-OS Python and remote workflows remain unverified | Engineering |
| Single builder review | Separate adversarial checks and browser verification; independent human review before release | Thomas |

## Material scope change: upcoming current-season forecasts (2026-10-24)

| Risk | Mitigation / acceptance | Owner |
|---|---|---|
| Current data accidentally downloads holdout | Season-specific URL only, reject 2024–2025 and mixed seasons before score parsing; no combined-file fallback | Engineering |
| Live scores mistaken for final results | Require explicit final phase, valid scores and observed-final timestamp before cutoff; no guessed completion time | ML maintainer |
| Late/corrected results leak into earlier forecasts | Immutable observation snapshots; identical-record evidence; no backdating; current/future/date perturbation tests | ML maintainer |
| Missing historical rows bias team state | Full regular-season/team coverage checks; unresolved prior games make affected forecasts unavailable | Engineering |
| Postponed/rescheduled/unconfirmed games | Stable source game-key, fingerprint/version change, no forecast without confirmed date/time/status; old snapshot warning | Engineering |
| Stale static forecasts look live | As-of and source update displayed; age limits and kickoff suppression; no silent automatic refresh promise | Product owner |
| Season-start priors mistaken for previous-year strength | Week 1 and low-history warnings; season reset; no prior-season input | ML maintainer |
| 2010–2022 model drifts in current season | Preserve model, disclose age/unvalidated current performance; no tuning or accuracy claim | Thomas |
| Provider availability/license scope | Document per-season release and repository license, attribution; upstream rights and public-release review remain separate | Thomas |
| Refresh automation enables unintended writes/costs | Disabled manual-only SHA-pinned template, read-only permissions, timeout, short retention, no deploy or paid resources | Thomas |

## Product execution and G4 risks (2026-10-24)

| Risk | Mitigation / residual limitation | Owner |
|---|---|---|
| Historical replay presented as prospective skill | Admit only immutable actual pregame records; retain publication status; zero completed forecasted games means zero prospective metrics | Engineering |
| Multiple refreshes distort aggregate metrics | Evaluate all snapshots but headline one designated final eligible pregame/game; disclose denominators and exclusions | ML maintainer |
| Result corrections silently alter history | Immutable new evaluation versions with final-result observation provenance; retain old records and explain changes | Engineering |
| Schedule delay makes a forecast look pregame | Compare original generation/cutoff and schedule identity against actual known kickoff; quarantine ambiguous schedule changes, never backdate | Engineering |
| Injury/starter/weather evidence arrives after cutoff | Explicit observed/published/effective time contracts, unavailable defaults, no unverified inputs in incumbent; adversarial late-evidence tests | ML maintainer |
| Selected 2023 or in-sample incumbent comparisons overstate challenger quality | Predeclare challenger windows; distinguish time-aware refit baselines from frozen in-sample diagnostics; preserve 2023 selection-exposed label | ML maintainer |
| Prior-season strength accidentally opens 2025 holdout | Protected-season guards at acquisition, dataset and inference boundaries; missing permitted prior state blocks affected challenger inference | ML maintainer |
| Narrative explains random outcomes as defects | Deterministic facts/hypotheses/verified defects separated; source timestamps; bounded evidence-only optional agent; no probability edits | Product owner |
| Successive challengers become uncontrolled tuning | Version protocols/runs, fixed criteria and measured ablations; periodic intentional runs, human promotion, registry and rollback | Thomas |
| Persistent observation cache lost between scheduled runs | Local retained immutable snapshots; prepared workflow restores only verified same-season artifacts after separate activation/retention review | Engineering |
| Local execution mistaken for public gate approval | Explicit local-record status, disabled scheduling/publication and candidate-only models; owner controls all G0–G4 decisions | Thomas |
