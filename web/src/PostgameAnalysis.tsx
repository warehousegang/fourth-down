import { loadOperations } from "./operations-contracts";
import { useArtifact } from "./use-artifact";
import { decimal, Heading, LoadState, Metrics, pct, Provenance, time } from "./IntelligenceShared";

export function PostgameAnalysis() {
  const evidence = useArtifact(loadOperations);
  if (!evidence.data) return <LoadState title="Postgame Analysis" error={evidence.error} retry={evidence.retry}/>;
  const { data, file, sha256 } = evidence.data;
  const completed = data.games.filter(g=>g.result);
  return <>
    <Heading label="OBSERVE · EVALUATE · INVESTIGATE" title="Postgame Analysis">All completed forecasted games are reconciled. Verified facts, research hypotheses and demonstrated limitations stay separate.</Heading>
    <Metrics value={data.metrics.primary} label="Final pregame forecast performance"/>
    <p className="current-context">Primary scoring uses one designated final pregame forecast per completed, non-tied game. {data.metrics.primary.ties_excluded} ties excluded. Each archived snapshot is also scored separately; repeated forecasts are not independent games.</p>
    {!completed.length && <section className="panel intelligence-empty"><div className="eyebrow">AWAITING VERIFIED OUTCOMES</div><h2>No completed forecasted games yet</h2><p>No recorded upcoming forecast has yet been reconciled with a verified final result. Historical results used for feature state are not counted as prospective predictions.</p><p>After kickoff, a local refresh can reconcile a verified final score. Until then, accuracy, Brier score, log loss and outcome explanations remain unestablished.</p></section>}
    {completed.map(g=>{
      const e = g.evaluations.find(x=>x.primary);
      return <article key={g.id} className="panel postgame-card"><div className="eyebrow">WEEK {g.week} · VERIFIED FINAL RESULT</div><h2>{g.away} {g.result!.away_score} <span className="muted">at</span> {g.home} {g.result!.home_score}</h2><p><a href={g.result!.source_url} target="_blank" rel="noreferrer">Result source</a> · Observed {time(g.result!.observed_at)}</p>{e ? <div className="postgame-score-grid"><div><span>Pregame {g.home} win</span><strong>{pct(e.home_probability)}</strong></div><div><span>Classification</span><strong>{e.correct ? "Correct" : "Incorrect"}</strong></div><div><span>Brier score</span><strong>{decimal(e.brier)}</strong></div><div><span>Log loss / surprise</span><strong>{decimal(e.log_loss)} nats</strong></div></div> : <p className="current-warning">{g.result!.tie ? "Tie: excluded from the binary win-probability metrics." : "No eligible final pregame forecast. This result is not added to primary model metrics."}</p>}
      {g.analysis && <div className="postgame-evidence"><section><h3>Verified game facts</h3><ul>{g.analysis.facts.map((f,i)=><li key={i}>{f.text} <a href={f.source_url} target="_blank" rel="noreferrer">Source</a><small>Observed {time(f.observed_at)}</small></li>)}</ul></section><section><h3>Hypotheses to investigate</h3>{g.analysis.hypotheses.length ? <ul>{g.analysis.hypotheses.map((h,i)=><li key={i}>{h.text}<small>Evidence needed: {h.evidence_needed}</small></li>)}</ul> : <p>No unsupported explanation has been generated.</p>}<p className="muted">Hypotheses are not verified causes. An unexpected result alone does not prove a model defect.</p></section><section><h3>Demonstrated model limitations</h3>{g.analysis.deficiencies.length ? <ul>{g.analysis.deficiencies.map(d=><li key={d}>{d}</li>)}</ul> : <p>No additional deficiency demonstrated by this game.</p>}</section></div>}
      <a href="#history">Inspect the original forecast history</a></article>;
    })}
    <section className="panel"><div className="eyebrow">BOUNDED RESEARCH</div><h2>Evidence before explanation</h2><p>The implemented analyst is deterministic. It reports verified score facts, measured forecast error and clearly labeled follow-up hypotheses. Quarterback performance, turnovers, injuries and weather remain unverified unless a separately reviewed evidence source supplies them.</p><p>A future research agent may attach citations and timestamps; it cannot change a recorded probability, invent statistics or promote a model. No paid LLM calls are used.</p></section>
    {data.warnings.map(w=><p className="current-warning" key={w}>{w}</p>)}
    <Provenance label="Postgame reconciliation" directory="operations" file={file} hash={sha256} generated={data.generated_at} retry={evidence.retry}/>
  </>;
}
