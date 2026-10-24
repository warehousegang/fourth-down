# Architecture
```mermaid
flowchart LR
 A[nflverse schedules] --> B[Explicit acquisition: whitelist seasons and fields]
 B --> C[Ignored local snapshot + SHA256 manifest]
 C --> D[Temporal features: earlier days only]
 D --> E[Training 2010–2022 / validation 2023]
 E --> F[Versioned coefficients + evaluation]
 F --> G[Separate deterministic forecast generation]
 G --> H[Schema-validated static JSON]
 H --> I[React / TypeScript / Vite]
 I -. human approval .-> J[GitHub Pages project]
 K[Future cited research] -. facts only, no probability edits .-> I
```
Training, forecast generation, and rendering are separate commands/components. Source data is untrusted: whitelist columns; reject duplicate IDs, incomplete outcomes, invalid dates and protected seasons. Fitting statistics use training only. Generated artifacts carry source/model/feature identifiers and timestamps. Browser validates the contract before rendering; no raw HTML or external requests besides its own static JSON. Model explanations sum coefficient × feature contributions in log-odds; they are not causal effects.

No database or application server. Raw data and model intermediates are ignored. The checksummed compact 2023 demo is tracked for clean-checkout builds; public redistribution still requires G3 approval. The additive holdout protocol and exposure record are distinct from the unchanged candidate artifacts. CI is manual-only, bounded and does not train/download data or deploy. Deployment workflow is a disabled template. Hash routes support refresh. Vite base is configurable. Research is a documented, unimplemented boundary.
