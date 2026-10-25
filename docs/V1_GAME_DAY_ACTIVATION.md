# V1 game-day activation — October 25, 2026

The owner authorized the prepared bounded schedule on October 25, after the game-day UI and verified Steelers–Saints result were published. This approval supersedes the review-only activation boundary in V1_GAME_DAY.md.

## Deployment

Use the existing `fourth-down-scheduler`, existing encrypted GitHub binding and manual-only portfolio refresh workflow. The approved configuration is `ENABLED=true` and exactly one cron: `2,17,32,47 * * * *`. No new scheduler, route, credential scope, paid plan, storage or compute product is introduced.

The existing dispatcher checks every 15 minutes from kickoff minus 15 minutes through kickoff plus 24 hours, ending that game's window on verified completion, cancellation or postponement. Outside those windows, and when the public schedule hint is invalid or unavailable, only minute 17 dispatches. At most 96 Worker invocations/day and three external requests/invocation are possible. GitHub run-history duplicate suppression, workflow concurrency and no-change publication remain intact.

The authenticated Cloudflare Workers plans page confirmed **Free / $0 / Current plan** before activation. Both repositories are public and use standard hosted Ubuntu runners. No plan or permission change is needed.

## Browser timestamps and state

Kickoff transitions use the local clock even if no backend artifact changes. An elapsed scheduled kickoff alone says **Awaiting result update**, never confirmed live status. Original probabilities and forecast timestamps remain archived.

Visible tabs poll verified published artifacts every 60 seconds, pause when hidden, and fetch on return. **Results last checked** is explicitly the latest successful fetch of published results by that browser. It advances even when the validated artifact is unchanged, and does not advance on failures. It is not a claim that the upstream provider was queried at that moment. **Result provider last published** and **Last verified results update** remain separate evidence timestamps. This avoids an unnecessary Pages rebuild solely to renew a clock. Backend collection times remain available in each refresh run's receipt.

## Release and verification

Keep the source pin and compiled application in the same portfolio commit. Hydrate the latest retained portfolio forecast and result bundles before building; a frontend-only release must not infer new predictions. Preserve all immutable public evidence and both retained archives byte for byte.

Before activation: run the no-fit Python suite, frontend and release suites, desktop/mobile lifecycle checks and scheduler tests. Perform one remote scheduled preview of the prepared Worker, verify its GitHub run, then deploy this configuration to the existing Worker. Verify the first real cron event separately from the controlled rehearsal, including scheduled time, dispatch time, provider capture receipt and publication/no-change result.

Rollback: retain prior Worker version `3f4176e8-6c0b-4581-a9d1-083578303fc0` and restore its single hourly cron `17 * * * *`. Do not run a parallel scheduler. Preserve all later forecast and result evidence during any frontend rollback, and restore source pin plus compiled assets together. The independent V2 Worker and research remain untouched.
