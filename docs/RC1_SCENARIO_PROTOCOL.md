# RC1 synthetic lifecycle scenario protocol

This harness verifies software behavior using controlled test fixtures. It does not measure NFL predictive accuracy. Every game ID contains `synthetic`, every source URL uses `example.invalid`, and every source/report identifies itself as synthetic. Scores are fixed test inputs, never represented as real NFL results or sampled from the Bernoulli uncertainty simulator. The fixed virtual October 2026 clock demonstrates execution ordering; these are not forecasts that were actually issued on those dates.

Run from the repository root:

```sh
python -m ml.lifecycle_simulation
python -m pytest tests/test_lifecycle_simulation.py -q
```

The CLI creates only a checksum-addressed evidence report under ignored `artifacts/rc1/scenarios/`. `--output-directory` permits that location or an operating-system temporary directory; production source/public paths and temporary symlinks pointing into them are rejected. Forecast generation and immutable forecast/operations publication run through the actual project functions inside a temporary directory. Those files are removed after their complete payloads and hashes are captured in the synthetic report. Public forecast pointers, captured real sources, model registry and frozen artifacts are never modified.

Four fixed earlier synthetic games produce ±20-point team margins. The actual frozen preprocessing produces a smoothed-win difference of ±0.5, cumulative-margin difference of ±20, recent-margin difference of ±26.6666666667 and zero rest difference. The unchanged coefficient vector and intercept produce home probabilities approximately 0.9228153987 and 0.1264352940. No coefficient or probability is changed to force a target value.

The fourteen independently checked scenarios cover a strong home favorite losing, a home underdog winning, a correct favorite, missing final result, postponement, corrected final score, late injury context, stale source, missing source, missing feature input, duplicate reconciliation, failed generation, in-progress game and tied final. Each uses the complete applicable sequence: generation, temporary immutable publication, reconciliation, scoring and bounded investigation. Outages and failed generation retain the last successful temporary pointer; missing/unconfirmed inputs yield unavailable scores rather than invented data.

The scalar oracle independently computes correctness, `(p-y)^2`, and `-log(p(observed winner))` without calling lifecycle score helpers. It verifies primary/all-snapshot populations and calibration-bin counts. Corrected scores produce a new result and evaluation version while preserving original forecasts and previous evaluation bytes. Duplicate events and repeated runs produce identical artifacts and count each final game once. Late injury annotations are rejected after cutoff and cannot affect probabilities. Investigation assertions require source/timestamp references, explicit evidence needs for hypotheses, no invented injury/weather/quarterback cause, no demonstrated model defect from one result and zero paid calls.

The machine-readable report includes every fixture, emitted artifact and checksum, status transition, failure message, numerical result and named assertion. Repeated runs are byte-identical for unchanged code/model inputs. Assertions fail the command rather than publishing a pass report. The accompanying adversarial tests also prohibit network/fitting, fingerprint public JSON before and after execution, challenge output-path restrictions, and inject an unexpected generation failure. Scenario success is evidence of functional and AI-behavioral correctness only; retrospective replay and genuine prospective performance remain separate evidence.
