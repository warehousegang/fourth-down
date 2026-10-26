# Weekly forecast intelligence — V1 review

This is a read-only frontend analysis of the existing checksummed operations artifact. It does not create forecasts, modify evaluations, fit a model, call another service, or change refresh scheduling. The banner appears above Prediction Scoreboard and updates through the same visible-tab artifact polling.

## Population and method

Use the selected week in the current prospective season. Include each game once, only after a verified, non-tied final and a designated, eligible pregame forecast with its primary evaluation. The designation is the lifecycle protocol's latest eligible pre-kickoff receipt, selected independently of the outcome; do not substitute another snapshot. All original forecasts, timestamps and results remain in their existing archives.

For each included game let p be its original home-win probability, q = max(p, 1−p), and y indicate a verified home win. The existing scorecard selects the home team at exactly p = 0.5.

- Expected correct picks: sum(q).
- Actual correct picks: count of correctly selected winners. Difference: actual − expected.
- Exact Poisson-binomial distribution: begin with mass[0] = 1. Convolve each Bernoulli(q), updating in descending order: mass[k] = old_mass[k](1−q) + old_mass[k−1]q. This requires O(n²) time and O(n) space; there is no simulation or random seed.
- Lower tail: sum of mass[k] for k from 0 through the observed correct count, inclusive. This assumes independent games and the supplied probabilities. It is not a probability that the model is defective, nor a calibrated significance claim.
- Realized probability: p for a home win, 1−p for an away win. Total outcome surprise: sum(−ln(realized probability)), in nats. Divide by n for mean surprise, identical to the existing log loss on the same rows. The existing 1e−15 logarithm floor is retained without changing any original probability.
- Model-expected total surprise: sum of binary entropy −p ln(p) − (1−p) ln(1−p). This is descriptive probability-based context, not an empirical calibration estimate or a tail probability for surprise.

The expected and observed quantities always use the **same scored subset**, including during incomplete weeks. Results that have not arrived do not count as losses. The full schedule supplies coverage counts, including games with no archived forecast. Pending games, ties, missing eligible predictions, postponed/canceled games and missing designated evaluations are shown separately. Zero scored games produce no numeric expectation or surprise claim. A corrected result recomputes the view using the same designated forecast; repeat renders do not add records.

The expandable distribution includes a keyboard-accessible numeric table. The three lowest-probability actual winners below 50% are shown with verified final scores, original probability, original save timestamp and a matchup-analysis link. They are model underdogs, not assertions about betting markets or causes of defeat.

## Interpretation and historical boundary

Small samples and uncertain calibration are explicit. Shared factors may make game outcomes dependent. A surprising outcome alone cannot distinguish chance variation from a systematic model defect; that requires accumulated prospective evidence and separate investigation. No accuracy target, “fluke” conclusion, causal story, or automatic model change is inferred.

No historical percentile is presented. The existing 2023 validation is retrospective and was used for model selection; the historical backtests use expanding training windows. Neither is a like-for-like collection of immutable prospective forecasts from this frozen V1 deployment. This view never reads historical raw data, protected holdouts, rehearsals, simulations or V2 shadow predictions. Historical validation remains on its separate page. A future historical comparison would require a declared comparable population and method, rather than mixing these sources.

## Week 7 review capture, October 26, 2026

Hosted data verified at approximately 9:09 AM EDT against portfolio commit `427b4b54d98f9009c46f744084e667840f80752c`, pinned production source `8851443dda24fca353f1e41522920d79bcde5c47`. The feature branch starts at source main `f0b38662271538c0375069dda8876f4d55c5eb86`.

Evidence: [published operations artifact](https://thomashoward.dev/fourth-down/data/operations/operations-75054d83c5e77bef3a96134c924e6924c172cbedeae43c28e450b253f978b2fc.json), SHA-256 `75054d83c5e77bef3a96134c924e6924c172cbedeae43c28e450b253f978b2fc`, generated October 25 at 11:33:57 PM EDT. Retained raw evidence was restored and validated using the existing hydrate path; no acquisition or forecast generation was run for this feature review.

| Quantity | Observed value |
|---|---:|
| Week 7 scheduled games | 14 |
| Scored games | 12 |
| Correct / incorrect | 5 / 7 |
| Expected correct | 7.395867732124277 |
| Actual minus expected | −2.3958677321242767 |
| P(correct ≤ 5) | 0.1280306070551856 (12.8%) |
| Total outcome surprise | 9.235708622233933 nats |
| Mean outcome surprise / log loss | 0.769642385186161 nats |
| Model-expected total surprise | 7.847939966952175 nats |
| Existing scoreboard accuracy | 41.6667% |
| Existing scoreboard Brier score | 0.2869351229086541 |

Dallas–Philadelphia is pending. New England–Chicago has no eligible archived prediction and is excluded. No ties or postponed/canceled games enter this sample. These are partial-week findings, not a forecast of the final weekly record. The lower tail is meaningful only under the stated model-probability and independence assumptions; it does not establish unusualness against a historical population.

All 12 designated forecasts below retain their original October 24, 2026, 8:22:38 PM EDT timestamp (`2026-10-25T00:22:38.161263+00:00`). Display values are rounded; calculations use the archived full precision.

| Verified final | Original pick | Pick probability | Pick result | Actual winner's original probability |
|---|---|---:|---|---:|
| PIT 16–NO 10 | PIT | 54.67% | Correct | 54.67% |
| SF 20–ATL 29 | SF | 66.57% | Incorrect | 33.43% |
| CIN 35–BAL 13 | BAL | 55.01% | Incorrect | 44.99% |
| TB 43–CAR 13 | CAR | 70.38% | Incorrect | 29.62% |
| NYG 27–HOU 21 (OT) | HOU | 55.71% | Incorrect | 44.29% |
| IND 10–MIN 16 | MIN | 78.15% | Correct | 78.15% |
| MIA 28–NYJ 25 | NYJ | 69.29% | Incorrect | 30.71% |
| CLE 27–TEN 24 | CLE | 55.98% | Correct | 55.98% |
| DEN 30–ARI 16 | DEN | 58.89% | Correct | 58.89% |
| GB 17–DET 20 | DET | 61.30% | Correct | 61.30% |
| LA 35–LV 21 | LV | 57.90% | Incorrect | 42.10% |
| KC 3–SEA 20 | KC | 55.74% | Incorrect | 44.26% |

Independent Python verification enumerated all 4,096 combinations for this 12-game sample. The browser regression independently enumerates the retained weekly sample and checks the rendered expected count, inclusive lower tail, scorecard count and mean surprise. Unit tests also enumerate a 16-game slate (65,536 combinations), check hand-expanded probabilities, certain outcomes, zero samples, corrections, ties, designation eligibility, 50% ties in prediction, missing results and the logarithm floor. Browser checks include keyboard disclosures, expanded/collapsed accessibility, mobile overflow, automatic final/correction updates, outage retention and existing portfolio behavior.

## Review and publication

Review verification: 198 frontend unit/integration tests, 564 Python no-fit tests (six explicit skips for unavailable historical raw snapshots), 11 release checks and eight unchanged scheduler tests passed. The full integrated Chrome suite passed 58 desktop/mobile tests; the final banner CSS adjustment also passed both targeted desktop/mobile checks. The production build passed; npm audit reported zero vulnerabilities. Accessibility checks cover WCAG 2 A/AA and 2.1 AA, native keyboard disclosures and 320px mobile overflow.

Integrity checks matched 78 public data files and both retained forecast/result evidence bundles byte-for-byte with the production baseline. All 32 logos, protected model/research files, scheduler configuration, dependencies, and all 50 portfolio files outside the application remained unchanged. The derived review capture and screenshots are supporting evidence, not additional forecast or scorecard artifacts.

No deployment is authorized by this change. Review the source implementation and desktop/mobile previews first. After explicit publication approval, fetch the latest portfolio main, hydrate its newest retained evidence, rebuild from the approved source revision and run the existing release/browser checks. Update the immutable source pin **and compiled frontend together** in the existing portfolio workflow integration, preserving every intervening forecast/result artifact. A source-only merge will not deploy this feature; publishing only compiled assets would allow an automated refresh at the old pin to revert it. Keep scheduling, V2, models, logos, historical content and all portfolio pages unchanged.
