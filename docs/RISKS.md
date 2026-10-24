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
| Cost or accidental deployment | No automatic workflows, no deploy until approval | Thomas |
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
