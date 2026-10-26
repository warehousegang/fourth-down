import { weeklyIntelligence } from "./weekly-intelligence";
import type { Operations } from "./operations-contracts";
import { time } from "./IntelligenceShared";
import { team } from "./teams";

const percent = (p: number) => p > 0 && p < .001 ? "<0.1%" : `${(p * 100).toFixed(1)}%`;

export function WeeklyIntelligence({ operations, week }: { operations: Operations | null; week: number | null }) {
  if (!operations || week === null) return null;
  const s = weeklyIntelligence(operations, week);
  const delta = s.difference;
  const title = delta === null ? "Awaiting verified outcomes" : Math.abs(delta) < .005 ? "Picks matched expectation"
    : delta < 0 ? "Picks trailed expectation" : "Picks exceeded expectation";
  return <section className="panel weekly-intelligence" aria-labelledby="weekly-intelligence-title">
    <div className="weekly-overview">
      <div className="weekly-copy"><div className="eyebrow">WEEK {week} INTELLIGENCE · {s.season} PROSPECTIVE V1</div>
        <h2 id="weekly-intelligence-title">{title}</h2>
        <p>{s.count ? Math.abs(delta!) < .005 ? "Observed picks match the probability-based expectation to two decimal places." : <>{Math.abs(delta!).toFixed(2)} {delta! < 0 ? "fewer" : "more"} correct picks than expected from the saved probabilities.</>
          : "The analysis appears after eligible saved predictions have verified, non-tied final results."}</p>
        <span className="weekly-coverage">{s.partial ? "Partial week" : "Week settled"} · {s.count} scored · {s.pending} pending</span>
      </div>
      {s.count > 0 && <dl className="weekly-numbers">
        <div><dt>Correct picks</dt><dd>{s.correct}<small> / {s.count}</small></dd></div>
        <div><dt>Expected correct</dt><dd>{s.expected!.toFixed(2)}</dd></div>
        <div className="weekly-tail"><dt>Chance of {s.correct} or fewer</dt><dd>{percent(s.lowerTail!)}</dd></div>
      </dl>}
    </div>
    <p className="weekly-caveat">Model-based context, not proof of a defect. The count calculation assumes independent games and takes the saved probabilities at face value; calibration is uncertain.</p>
    <details className="weekly-details"><summary>Explore the week’s outcomes &amp; method</summary>
      <div className="weekly-analysis">
        <section aria-label="Correct-pick distribution"><h3>How many correct picks were plausible?</h3>
          {s.count ? <>
            <p>For these {s.count} scored games, the exact Poisson-binomial calculation gives a {percent(s.lowerTail!)} chance of {s.correct} or fewer correct picks. This is a lower-tail probability, not the probability that the model is wrong.</p>
            <div className="weekly-distribution" aria-hidden="true">{s.distribution.map((p, k) => <div key={k} className={k === s.correct ? "weekly-observed" : ""}><span style={{height:`${p / Math.max(...s.distribution) * 88}px`}}/><small>{k}</small></div>)}</div>
            <p className="weekly-chart-note">Correct-pick count · gold bar = observed {s.correct}</p>
            <details className="weekly-distribution-table"><summary>Exact distribution values</summary><table>
              <caption>Model-implied correct-pick distribution for {s.count} scored games</caption>
              <thead><tr><th scope="col">Correct picks</th><th scope="col">Probability</th></tr></thead>
              <tbody>{s.distribution.map((p, k) => <tr key={k}><th scope="row">{k}{k === s.correct ? " (observed)" : ""}</th><td>{(p * 100).toFixed(6)}%</td></tr>)}</tbody>
            </table></details>
          </> : <p>No scored sample yet. A probability of surprise would be misleading.</p>}
        </section>
        <section aria-label="Outcome surprise"><h3>How surprising were the winners?</h3>
          {s.count ? <><p className="weekly-surprise"><strong>{s.meanSurprise!.toFixed(4)}</strong> nats per game</p>
            <p>Mean outcome surprise is the log loss of the probabilities assigned to the actual winners. Total: <strong>{s.totalSurprise!.toFixed(4)} nats</strong>; model-expected total for the same games: {s.expectedSurprise!.toFixed(4)} nats. Higher values mean less probability was assigned to the outcomes that occurred.</p></> : <p>Outcome surprise is unavailable until a game can be scored.</p>}
          <p>A surprising week alone cannot establish a model defect or calibration failure. Shared factors can make games dependent; a small sample cannot distinguish chance variation from systematic error.</p>
          <p>No historical percentile is claimed. The <a href="#performance">2023 retrospective validation</a> has different forecast provenance and stays separate from this prospective record. Simulations and V2 shadow picks are excluded.</p>
        </section>
      </div>
      {s.upsets.length > 0 && <section className="weekly-upsets" aria-label="Notable model underdogs"><h3>Lowest-probability winners</h3><p>Model underdogs, ranked by their original win probability. Verified final scores; no causal explanation is inferred.</p>
        <ol>{s.upsets.slice(0, 3).map(r => <li key={r.game.id}>
          <a href={`#intelligence?game=${encodeURIComponent(r.game.id)}`}>{team(r.winner).name} won <strong>{(r.realizedProbability * 100).toFixed(2)}%</strong></a>
          <span>{r.game.away} {r.game.result!.away_score} · {r.game.home} {r.game.result!.home_score} · Final</span>
          <small>Pregame win probability · saved <time dateTime={r.forecast.generated_at}>{time(r.forecast.generated_at)}</time></small>
        </li>)}</ol>
      </section>}
      <section className="weekly-method" aria-label="Weekly analysis coverage and method"><h3>Sample &amp; calculation</h3>
        <p>{s.total} scheduled games: {s.count} scored, {s.pending} awaiting verified results, {s.ties} ties excluded, {s.missing} without an eligible archived prediction, {s.held} postponed or canceled, {s.unscored} awaiting a designated evaluation. {s.partial ? "This is an incomplete week; expected and actual picks use only the scored subset, not the full slate." : "Only the scored subset enters these calculations."}</p>
        <p>One designated pregame forecast per game, with the original probability and timestamp. Expected correct picks = sum of each pick’s win probability; actual minus expected is the difference. At exactly 50%, the existing scorecard’s home-team pick is used. Ties are excluded because V1 probabilities condition on a non-tied outcome.</p>
        <p>Exact deterministic convolution calculates every possible correct-pick count. Outcome surprise = sum of −ln(probability of the verified winner); its per-game mean equals log loss. Model-expected surprise sums binary entropy. The logarithm uses the existing scorecard’s 10⁻¹⁵ floor; saved probabilities are unchanged. A score correction recomputes this view from the same designated forecast.</p>
      </section>
    </details>
  </section>;
}
