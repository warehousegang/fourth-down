# Historical implementation review — 2026-10-24

This record describes earlier development checks, including fitting that was NOT rerun during corrective release preparation. The owner subsequently accepted an independent review and disclosed prior legacy-baseline holdout exposure. Current evidence and remaining gates are in RELEASE_GATES.md and CORRECTIVE_VALIDATION.json. Artifact exclusion and mutable Action references described below have since been corrected. Statements about not executing the legacy baseline refer only to that earlier implementation pass, not the complete project history.

This was a separate adversarial review by the same implementation agent, not an independent human or external-agent review. Human review remains a release requirement. Self-authored tests alone are insufficient; the following additional evidence was used.

## Evidence beyond expected-value unit tests
- Executed the original feature function on restricted real historical input and compared every original feature to the new builder. Exact parity held; original scikit-learn metrics reproduced the supplied values.
- Compared exported raw-scale coefficients to the fitted scikit-learn pipeline's probabilities at 1e-12 tolerance, rather than trusting a duplicated scoring function.
- Independently queried the historical schedule for each home/away team for all 272 validation games and compared win-rate, season margin, recent margin and rest with the stateful feature builder. All matched.
- Refit the candidate twice from the verified snapshot; coefficients matched each other and the delivered artifact exactly.
- Inspected desktop and mobile renderings. Exercised selection, deep-link reload, failure states, all four screens and overflow at desktop/mobile sizes. Used axe checks with WCAG 2 A/AA and 2.1 AA tags on every screen, first on development then on the production subpath.
- Queried npm and Python package advisory databases. Both returned zero known vulnerabilities; Python audit covered all 41 pinned packages with no skips. This is a point-in-time advisory check, not proof of supply-chain safety.

## Findings fixed
1. Original baseline evaluates the protected holdout. Preserved it byte-for-byte, documented the hazard and built a validation-only harness; did not execute it.
2. Initial dependency choices had published vulnerabilities. Updated Zod and Vitest to patched releases; final audit clean.
3. Secondary labels failed text contrast and horizontal tables lacked keyboard focus. Corrected colors, added focusable named regions and visible outlines; reran all screens.
4. Mobile icon navigation needed accessible names; added explicit labels. Skip link now focuses main without changing the active hash route.
5. A malformed artifact could omit the comparison baseline and crash Performance. Runtime contract now requires exactly one of each contender and rejects tampering.
6. Source validation accepted fractional seasons/weeks. Added integral/range validation and adversarial tests.
7. Root data ignore rule originally also ignored frontend data implicitly. Replaced with explicit root rules and an intentional frontend-artifact exclusion pending owner inclusion/redistribution approval. Verified raw data, build output and dependencies remain ignored.

## Residual limitations
No vintage schedule snapshots; results can reflect later corrections. No independent final-test evidence or public approval. No separate human reviewer. One validation season, model selection on that season, sparse calibration tails, unmodeled injuries/QB/weather, neutral-venue home intercept, modest sample size. Removing smoothed win rate slightly improves validation Brier (0.236123 vs 0.237045); this was reported rather than hidden or used for another tuning cycle. Clean install on another OS and remote CI are not verified. Official Action version tags must be pinned to reviewed SHAs before activation. Python requirements are version-pinned but not wheel-hash locked.
