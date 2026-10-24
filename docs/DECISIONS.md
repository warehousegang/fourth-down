# Decisions
- ADR-001: Preserve five original scripts byte-for-byte under legacy/ with SHA256 manifest. Original repo has one initial commit; four analysis scripts are untracked. Do not alter its working tree. Owner selected the attached workspace as destination.
- ADR-002: Use assignment-provided Idea-to-Production stages/gates; full OS source unavailable. Tier A provisional, not a public-release approval.
- ADR-003: Historical 2023 replay avoids claiming future forecasts or inspecting protected 2024–2025 outcomes. Earlier-calendar-day cutoff is conservative and easy to test.
- ADR-004: Small schedule-only logistic model first. Efficiency, opponent adjustment, venue split and explicit bye flags deferred pending incremental evidence; rest captures some schedule information. No redundant feature accumulation or PBP download.
- ADR-005: Deterministic linear explanations, JSON coefficients and feature contributions; no pickle or paid LLM inference.
- ADR-006: Manual local training + static JSON + React. No persistent compute. Hash routing and configurable base isolate this project from the personal website.
- ADR-007: Manual-only CI, disabled deployment template; no remote mutations or workflow runs authorized.

- ADR-008 (owner-requested reskin, 2026-10-24): Follow the supplied dark forecast-lab reference: near-black canvas, neon-green accents, monospace typography, centered navigation and featured field card. Include local team logos with source/checksum provenance. Feature an actual 2023 Week 4 Detroit–Green Bay replay. Forecast JSON, trained model, and frozen evaluation stay unchanged.

- ADR-009 (corrective release, 2026-10-24): Preserve the original model freeze and all hashed files. Record partial 2024–2025 exposure, then freeze a separate scoring-only protocol before any further inspection. Candidate execution requires another explicit approval; no tuning, fitting or data acquisition is performed here.
- ADR-010: Establish local Git history, with cf15da8 preserving the frozen scientific baseline. This records the current state and cannot reconstruct or prove earlier experiment chronology.
- ADR-011: Supersede ADR-008 logo inclusion with original CSS text identifiers. Retain old provenance but exclude the image assets. Ship complete production dependency notices and preserve nflverse attribution.
- ADR-012: Track only the existing 2023 forecast JSON, check its hash and candidate equality, and pin all official Action dependencies by verified commit SHA. Keep deployment inactive. Use a no-fit test runner so testing cannot retrain the candidate.
