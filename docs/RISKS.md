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
