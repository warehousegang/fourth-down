# NYG–HOU overtime regression evidence

`2026_07_NYG_HOU.rds` is the unchanged, current-season nflverse provider file
published October 25, 2026 at 20:31:25 UTC. It explicitly reports
`FINAL_OVERTIME`, New York Giants 27, Houston Texans 21.

Source: https://github.com/nflverse/nflverse-pbp/releases/download/raw_pbp_2026/2026_07_NYG_HOU.rds

License: https://github.com/nflverse/nflverse-pbp/blob/master/LICENSE.md

SHA-256: `78afae9d13511b1ba4b3cbb8fdf26afb29281f88b7d5d114efba85a02521089d`

`2026_07_NYG_HOU.legacy.json` is the original observation retained by production
at 20:33:58.656615 UTC. Its old `unknown` interpretation is intentionally kept
unchanged to test compatibility and recovery. Tests must never publish these
fixtures. Neither fixture is a forecast, training input, or historical holdout.

## DEN–ARI terminal-evidence regression

`2026_07_DEN_ARI.rds` is the unchanged nflverse file published October 25, 2026
at 23:31:29 UTC. Its summary still says `INGAME`, quarter 4, 00:36, DEN 30–ARI 16.
The last play is explicitly `END_GAME` (ID and sequence 4858), quarter 4, 00:00;
the last drive has the matching `END_GAME` transition and terminal play ID, and
the scoring summary agrees with both totals. No elapsed-time or lead heuristic
is used to interpret this file.

Source: https://github.com/nflverse/nflverse-pbp/releases/download/raw_pbp_2026/2026_07_DEN_ARI.rds

License: https://github.com/nflverse/nflverse-pbp/blob/master/LICENSE.md

SHA-256: `a83eec0c2beb8aebda46dd2e5b35a6f736fdf64d8a979ea59346e50ea32f6480`

`2026_07_DEN_ARI.legacy.json` is the byte-for-byte observation retained in the
production result bundle at 23:48:29.756110 UTC. Revalidation may interpret its
raw file but must never rewrite its JSON, hash, scores or observation time.
The new interpretation is derived only after raw provenance validation and is
not serialized into the original receipt. Fixtures are never published.
