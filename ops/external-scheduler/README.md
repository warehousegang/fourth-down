# V1 game-day scheduler

The existing V1 Worker was activated with owner approval on October 25, 2026.
Its single cron is `2,17,32,47 * * * *`: dispatch every 15 minutes inside the
bounded game windows and hourly outside them. See
[the activation record](../../docs/V1_GAME_DAY_ACTIVATION.md).
Do not create a second scheduler or change the active configuration without review.

The implementation reuses the existing V1 Worker and secret, adding a bounded
game-window hint and 15-minute slots. It does not perform model inference,
publish the website, or modify the separate V2 scheduler.

Run offline checks with:

```sh
node --test ops/external-scheduler/dispatch.test.mjs
```

`fourth-down-refresh.yml.proposed` is an inactive portfolio workflow template.
Replace its source placeholder only with the reviewed immutable commit when
preparing the app and pin together. It installs the separate result dependencies,
skips builds on unchanged data and reuses compiled assets for outcome-only updates.

See [the V1 game-day handoff](../../docs/V1_GAME_DAY.md) for provider findings,
cost/latency limits, exact publication/activation steps, monitoring and rollback.
