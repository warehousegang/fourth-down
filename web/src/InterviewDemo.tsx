import { useState } from "react";
import type { ForecastRecord, Operations } from "./operations-contracts";
import { demonstrationForecasts, MAX_DEMO_DRAWS, researchWalkthrough, simulateBernoulli } from "./interview-demo";
import { pct, Table, time } from "./IntelligenceShared";
import { useForecastClock } from "./use-forecast-clock";

export function InterviewDemo({ data }: { data: Operations }) {
  const now = useForecastClock(data.catalog.flatMap(f => [f.kickoff, f.valid_until]));
  const forecasts = demonstrationForecasts(data, now);
  const [selected, setSelected] = useState("");
  const forecast = forecasts.find(f => f.id === selected) ?? forecasts[0];
  return <section className="panel interview-demo">
    <div className="eyebrow">INTERVIEW DEMONSTRATION</div>
    <h2>Explore a probability. Inspect the evidence.</h2>
    <p>A small browser demonstration using verified saved forecast inputs. Synthetic trials and research proposals stay separate from real performance.</p>
    <details><summary>Open simulation and research walkthrough</summary>
      {!forecast ? <p className="current-warning">No verified saved forecast matches an upcoming scheduled game. The demonstration requires a pregame record; it does not invent a matchup or probability.</p> : <>
        <label className="intelligence-select">Saved upcoming matchup<select aria-label="Demonstration matchup" value={forecast.id} onChange={e => setSelected(e.target.value)}>{forecasts.map(f => <option key={f.id} value={f.id}>{f.away} at {f.home}</option>)}</select></label>
        <DemoForForecast key={forecast.id} forecast={forecast} now={now} />
      </>}
    </details>
  </section>;
}

function DemoForForecast({ forecast: f, now }: { forecast: ForecastRecord; now: number }) {
  const [count, setCount] = useState("10000");
  const [seed, setSeed] = useState("42");
  const [result, setResult] = useState<ReturnType<typeof simulateBernoulli> | null>(null);
  const [error, setError] = useState("");
  const [stage, setStage] = useState(0);
  const walkthrough = researchWalkthrough(f);
  const artifactURL = `${import.meta.env.BASE_URL}data/current/${f.artifact_file}`;
  const expired = now >= Date.parse(f.valid_until);
  function simulate() {
    try {
      if (!/^\d+$/.test(count) || !/^\d+$/.test(seed)) throw new Error("Count and seed must be whole numbers; empty, negative or fractional values are invalid.");
      setResult(simulateBernoulli(f.home_probability!, Number(count), Number(seed)));
      setError("");
    } catch (problem) { setResult(null); setError(problem instanceof Error ? problem.message : "Invalid simulation inputs."); }
  }
  return <>
    <p><strong>Saved home-win estimate: {pct(f.home_probability)} for {f.home}.</strong> Recorded {time(f.generated_at)} · cutoff {time(f.cutoff)} · kickoff {time(f.kickoff)}.</p>
    <p className={expired ? "current-warning" : "muted"}>{expired ? "This saved forecast has expired. The demonstration uses its archived probability; it is not a fresh current forecast." : "This is the saved estimate, not a live refresh. Schedule changes after the source observation are not checked here."}</p>
    <p><a href={artifactURL} download>Download cited forecast inputs</a> · Model {f.model_id}</p>
    <details><summary>Saved artifact checksum</summary><p className="intelligence-hash">{f.artifact_sha256}</p></details>
    <h3>1. Seeded outcome simulation</h3>
    <p>Each trial is one synthetic home win or away win, conditional on a non-tied outcome and the fixed saved probability. No game scores are generated.</p>
    <div className="demo-controls">
      <label>Simulation draws<input aria-label="Simulation draws" type="number" min="1" max={MAX_DEMO_DRAWS} step="1" value={count} onChange={e => { setCount(e.target.value); setResult(null); setError(""); }} /></label>
      <label>Simulation seed<input aria-label="Simulation seed" type="number" min="0" max="4294967295" step="1" value={seed} onChange={e => { setSeed(e.target.value); setResult(null); setError(""); }} /></label>
      <button className="current-reload" onClick={simulate}>Run synthetic trials</button>
    </div>
    {error && <p role="alert">{error}</p>}
    {result && <section aria-label="Synthetic simulation result" aria-live="polite">
      <p><strong>{result.wins.toLocaleString("en-US")} synthetic {f.home} wins · {result.losses.toLocaleString("en-US")} synthetic {f.away} wins</strong> in {result.count.toLocaleString("en-US")} trials.</p>
      <p>Home-win frequency {pct(result.frequency)} · fixed input {pct(result.probability)} · conditional sampling standard error {(result.standardError * 100).toFixed(3)} percentage points.</p>
      <p className="muted">{result.algorithm} · seed {result.seed} · bounded to 100,000 draws. Identical inputs and seed reproduce identical counts. This browser generator differs from the local Python validation harness.</p>
    </section>}
    <p className="current-warning">Synthetic outcomes do not validate model accuracy, calibration or true game probability. Sampling uncertainty assumes the supplied probability is correct; model and data uncertainty remain outside this demonstration.</p>
    <h3>2. Evidence-led research walkthrough</h3>
    <p>Deterministic template: plan → inspect → hypotheses → human proposal. No LLM, autonomous agent, new data retrieval or model editing runs here. Injuries, quarterback news and weather are not inspected by this walkthrough and do not affect the frozen model.</p>
    {stage > 0 && <ol className="demo-research-steps" aria-label="Research walkthrough steps">
      <li><h4>Plan</h4><p>{walkthrough.plan}</p></li>
      {stage > 1 && <li><h4>Inspect cited inputs</h4><p>Exact saved feature differences and log-odds contributions from <a href={artifactURL}>the cited forecast</a>. These describe the model calculation, not causal effects.</p><Table label="Research walkthrough saved factors"><thead><tr><th>Feature</th><th>Home minus away</th><th>Log-odds contribution</th></tr></thead><tbody>{f.factors.map(factor => <tr key={factor.key}><th>{factor.label}</th><td>{factor.difference.toFixed(4)}</td><td>{factor.contribution.toFixed(4)}</td></tr>)}</tbody></Table></li>}
      {stage > 2 && <li><h4>Draft a testable hypothesis</h4><p>{walkthrough.hypothesis}</p><p><strong>Evidence needed:</strong> {walkthrough.evidenceNeeded}</p></li>}
      {stage > 3 && <li><h4>Human proposal</h4><p>{walkthrough.proposal}</p></li>}
    </ol>}
    {stage < 4 ? <button className="current-reload" onClick={() => setStage(stage + 1)}>{["Plan research", "Inspect saved inputs", "Draft hypothesis", "Prepare human proposal"][stage]}</button> : <button className="current-reload" onClick={() => setStage(0)}>Reset research walkthrough</button>}
  </>;
}
