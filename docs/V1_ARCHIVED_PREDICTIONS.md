# V1 archived pregame display maintenance

This correction starts from deployed source `5b36e59375fa23dfefcc862b40e5280234587caa`, whose tree matches source main `ea18d5f6a05b51dcc4ea340bb0d6412f25c00f1b`. It changes display selection and presentation only. Frozen inference, result reconciliation, evaluation selection, protocols, immutable artifacts, team logos and scheduling are unchanged. V2 research is outside this branch.

## Incident and cause

At kickoff, `selectDisplayForecast` (and its Python policy mirror) returned unavailable before consulting the verified archive. It also required a scheduled game and the same raw source checksum as current inference. Those requirements are appropriate for a current estimate, but result observations naturally change the source checksum. Separately, `ml.current.generate` correctly removes started games from upcoming inference. A current-only card list therefore lost the matchup on the next refresh.

The retained production receipt for `ngs-2026-60272` is `b3e511b6096aded40a2c62638e3fb0c34a61e476ba671eb8649b80cd304c1a59`, in `forecast-2026-a692ad1ca1e530541125ad849f886cf52ab84764e82473c03c9f5f2aaa713e86.json`. It was generated `2026-10-25T00:22:38.161263+00:00` (October 24, 8:22 PM EDT), with Pittsburgh 0.5467062741859874 and New Orleans 0.45329372581401256. Subsequent stale-source attempts contain no probability; they did not overwrite this receipt. The UI keeps its established one-decimal display; the downloaded original JSON retains full precision.

## Display behavior

- Pregame: existing freshness and unchanged-input checks still apply; select the latest eligible receipt by generation time and ID.
- Kickoff: display an eligible archived receipt with its original timestamp and inputs, explicitly labeled “Archived pregame prediction.” A passed clock alone never claims live play or a final result.
- Refresh: join verified schedule/ledger entries into the card list, retaining the current week, most recent started week and unresolved games. Older games remain in Forecast History and accessible through explicit matchup links.
- Postgame: respect the operations artifact's `final_forecast_id`. Show the verified score, winner, classification, Brier and log loss belonging to that exact designation. Before designation, the display can select the latest eligible receipt without writing a designation.
- Missing evidence or prediction: show an unavailable explanation and history link. Postponed/canceled or changed schedule identities never inherit a prediction for the old schedule as a valid new one. The original is preserved in Forecast History.
- Delayed/unverified results: retain the archive without inventing scores. Ties remain unscored. Corrected results are read from a newer verified operations artifact; prior artifacts and forecasts stay unchanged.

The frontend does not perform inference, write history, or calculate evaluation metrics. The Python display helper mirrors selection; the existing forecast and reconciliation producers are unchanged.

## Verification and publication

Run `python scripts/test_release.py`, `npm test`, `npm run test:release`, `npm audit --audit-level=moderate`, the production build, and desktop/mobile Playwright tests. The lifecycle regressions cover the kickoff boundary, live play, delayed finals, final/corrected scores, ties, missing predictions, postponement/cancellation, refresh removal, week rollover, and archived deep links. Synthetic scores are test-only and must never enter public artifacts.

For a review build, hydrate the isolated checkout from the latest verified portfolio evidence using `scripts.automated_refresh.hydrate`; do not run acquisition or forecast generation for a display-only rehearsal. Build and package with `scripts/portfolio_artifact.py pack --generated-only`, then install into a separate local portfolio checkout. Verify all retained data/evidence and all non-application portfolio files are byte-identical.

Publication requires explicit owner approval. After approval, refresh the release rehearsal from the then-current portfolio state, update the portfolio workflow's immutable source pin to the reviewed maintenance commit, and publish the checked application through the existing process. Updating only compiled assets would let the next scheduled run restore the defective frontend. Preserve all existing forecast/evaluation versions and `.fourth-down-state`; do not change Cloudflare scheduling or unrelated portfolio content. Recheck for concurrent portfolio updates before publication. No deploy or workflow dispatch is part of this review.
