# V1 game-day scheduler proposal

This directory is a review candidate. `wrangler.json` is deliberately disabled
and has no triggers. The production Worker continues on its existing hourly
version. Do not deploy this directory or enable its cron without owner approval.

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
