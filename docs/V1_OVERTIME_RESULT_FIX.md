# V1 overtime-result publication correction

## Incident and verified evidence

On October 25, 2026, production source `c984550e8df414d9852b4549dd295a2754822c08`
left Giants–Texans (`ngs-2026-60276`) awaiting a result despite retaining the
approved nflverse final: **NYG 27, HOU 21**.

- Provider asset `2026_07_NYG_HOU.rds`, ID `676051652`, was published at
  **20:31:25 UTC / 4:31:25 PM EDT**. Its explicit phase is `FINAL_OVERTIME`.
- Original immutable observation: **20:33:58.656615 UTC**. Its raw SHA-256 is
  `78afae9d13511b1ba4b3cbb8fdf26afb29281f88b7d5d114efba85a02521089d`.
- Provider event `aad59e95-4feb-11f1-abca-2c54536568a9`, season 2026, week 7,
  away NYG, home HOU; scheduled kickoff 17:00 UTC, actual start 17:02:56 UTC.
- [4:32 PM refresh](https://github.com/warehousegang/thomashowarddev/actions/runs/40231246949)
  captured three observations and published other verified results in portfolio
  commit `ceeee840beb76ba71ce60503ac8bab81297c0879`. Pages built at 20:37:47 UTC.
- [5:02 PM refresh](https://github.com/warehousegang/thomashowarddev/actions/runs/40233574422)
  and [5:17 PM refresh](https://github.com/warehousegang/thomashowarddev/actions/runs/40234786063)
  succeeded. Their decision receipts report `captured: 0`, `changed: false`,
  and no requested Pages build. The NYG–HOU asset was already retained.

The parser recognized `FINAL OVERTIME` with a space but not `FINAL_OVERTIME`.
It retained the actual scores with `validated: false`, `status: unknown`.
Reconciliation skipped unknown observations. Duplicate suppression correctly
avoided downloading identical bytes on subsequent runs. This was a parser and
reconciliation failure, not missing provider data, mismatched identity, a
failed scheduler, or stale browser caching.

## Correction and immutability

Recognize the exact overtime alias in the supplemental results reader only.
Keep the raw phase unchanged. Validate old receipts against their exact prior
representation and interpret the proven overtime final when deriving new
operations. Both reconciliation and bundle validation use that interpretation.

No original observation, raw file, forecast, timestamp, or designation is
rewritten. The new operations artifact receives the current reconciliation
time and references the original observation digest and observation time.
Replaying the same evidence produces no second change. Normal duplicate
suppression, corrected-score precedence, and independent result collection
remain in place. Forecast/model code, V2 research, logos, and scheduling are
outside this correction.

## Real-data replay and browser verification

The complete retained production ledger was replayed locally. Only NYG–HOU
changed; all 80 original evidence files and 45 protected file hashes (including
32 logos) remained identical. The corrected full archive encoded, decoded, and
validated successfully. Reconciliation was idempotent.

Designated forecast `ab32c15bb95ede1a245a21f73a7f6791085ac26bf4afbf0b53f78b7544f4256a`:

- Saved October 24 at **8:22:38 PM EDT**, before kickoff.
- HOU probability **0.5571244457483405**, NYG **0.4428755542516595**.
- Predicted HOU; actual NYG; **incorrect**.
- Independently calculated Brier **0.31038764805039565** and log loss
  **0.814466464311742 nats**.

| Metric | Public site at 5:27 PM EDT | Corrected local replay |
| --- | ---: | ---: |
| Games scored | 7 | 8 |
| Correct / incorrect | 3 / 4 | 3 / 5 |
| Pending | 6 | 5 |
| Accuracy | 42.8571% | 37.5% |
| Brier | 0.3097334847312099 | 0.3098152551461081 |
| Log loss | 0.817451150419371 | 0.8170780646559174 |

Both weekly and season-to-date prospective populations match these values.
Desktop and mobile public-browser checks confirmed the original prediction,
the still-pending card, all 32 logo assets, no JavaScript errors, and successful
automatic published-artifact fetches. Public results were not changed.

Validation: 412 Python checks passed under the no-fitting guard (four checks
requiring separately retained historical snapshots skipped); 178 frontend
checks, 11 release checks, 48 desktop/mobile application browser checks, and
eight scheduler checks passed. Regression cases include the actual provider
RDS and legacy receipt, cache recovery, delayed publication, nonfinal overtime,
corrected overtime scores, duplicate suppression, tampering, and bundle restore.

The separate hosted portfolio run passed six tests. Two route tests reached a
local-host-only assertion that `/CNAME` should be publicly served; GitHub Pages
returns 404 there. Their preceding portfolio-page and asset checks passed.
Use the Pages API and retained `CNAME` configuration to verify the custom domain.

## Publication boundary and next action

**Review only: this correction is not deployed.** Routine reruns of the current
pin cannot recognize the retained overtime result. After approval, merge the
source correction, update the portfolio's immutable source pin together with
the checked application and result artifacts, and publish through the existing
Pages workflow. Rehydrate the latest retained evidence at release time; do not
replace it with the incident fixture or an older replay artifact.

Confirm the live NYG 27–HOU 21 card, unchanged original forecast, incorrect
classification, weekly/season aggregates, and a subsequent no-change refresh.
Do not change the scheduler, introduce a manual score override, backdate an
observation, fit a model, or alter V2.
