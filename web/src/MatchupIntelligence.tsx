import { ArrowRight } from "lucide-react";
import { loadCurrent } from "./current-contracts";
import { loadOperations } from "./operations-contracts";
import { selectDisplayForecast, displayRecord, displayGames } from "./forecast-display";
import { loadResearch, type Domain } from "./research-contracts";
import { useArtifact } from "./use-artifact";
import { Heading, LoadState, pct, Provenance, Table, time } from "./IntelligenceShared";
import { ForecastOutcome } from "./ForecastOutcome";
import { team } from "./teams";
import { useForecastClock } from "./use-forecast-clock";
import { CurrentContext } from "./CurrentContext";

export function MatchupIntelligence({ selectedId }: {selectedId:string|null}) {
  const current=useArtifact(loadCurrent,60_000);
  const operations=useArtifact(loadOperations,60_000);
  const research=useArtifact(loadResearch);
  const now=useForecastClock(current.data ? [current.data.data.valid_until,...current.data.data.games.map(g=>g.kickoff)] : []);
  if(!current.data)return <LoadState title="Matchup Intelligence" error={current.error} retry={current.retry}/>;
  const {data,file,sha256}=current.data;
  const games=displayGames(data,operations.data?.data??null,now,selectedId);
  const game=games.find(g=>g.id===selectedId)??games[0];
  const choice=game?selectDisplayForecast(data,game,operations.data?.data??null,now):null;
  const record=choice?displayRecord(operations.data?.data??null,choice):null;
  const view=record??(game && "cutoff" in game ? game : null);
  const reason=choice?.reason;
  return <>
    <Heading label="KNOWN INPUTS · VISIBLE GAPS" title="Matchup Intelligence">The model explains its actual inputs. Broader football intelligence stays separate from the probability until a validated model includes it.</Heading>
    {!game?<section className="panel"><h2>No upcoming matchup</h2><p>A confirmed current-season matchup is required to show team inputs.</p></section>:<>
      <label className="intelligence-select">Compare teams <select value={game.id} onChange={e=>{window.location.hash=`intelligence?game=${encodeURIComponent(e.target.value)}`;}}>{games.map(g=><option key={g.id} value={g.id}>Week {g.week} · {g.away} at {g.home}</option>)}</select></label>
      <section className="panel"><div className="eyebrow">WEEK {game.week} · {time(game.kickoff)}</div><h2>{team(game.away).name} at {team(game.home).name}</h2><p className="muted">{game.stadium} · Feature cutoff {time(view?.cutoff??null)} · Forecast generated {time(view?.generated_at??null)}</p>{reason || !view?<p className="current-warning">Current probability unavailable: {reason}</p>:<div className="intelligence-team-comparison"><div><span>{game.away} · AWAY</span><strong>{pct(view.away_probability)}</strong><p>{view.history.away.length} earlier completed current-season games</p></div><div><span>{game.home} · HOME</span><strong>{pct(view.home_probability)}</strong><p>{view.history.home.length} earlier completed current-season games</p></div></div>}
      {record&&<p className="game-day-note"><strong>Pregame prediction</strong> · Saved {time(record.generated_at)}. This probability stays fixed after kickoff; recent injuries, weather and news are not included.</p>}
      <ForecastOutcome game={game} operations={operations.data?.data??null} record={record} now={now}/>
      <h3>The four frozen predictive factors</h3><p>Values below belong to this archived input snapshot{reason?"; see the availability explanation above":""}. Rest is capped at 14 days. Smoothed rates and margins include the model’s fixed shrinkage.</p>{view?.factors.length?<Table label="Current matchup model factors"><thead><tr><th>Factor</th><th>{game.away}</th><th>{game.home}</th><th>Home − away</th><th>Log-odds contribution</th></tr></thead><tbody>{view.factors.map(f=><tr key={f.key}><th>{f.label}</th><td>{f.away.toFixed(4)}</td><td>{f.home.toFixed(4)}</td><td>{f.difference.toFixed(4)}</td><td>{f.contribution.toFixed(4)}</td></tr>)}</tbody></Table>:<p className="current-warning">A required observation is unavailable. No input or contribution is imputed for this matchup.</p>}<p>Home-win probability = logistic({data.model.intercept.toFixed(6)} + the four contributions). Positive contributions favor the home team. These are model associations, not causal claims.</p><a href="#history">View forecast versions <ArrowRight size={14}/></a></section>
    </>}
    {game&&"cutoff" in game&&<CurrentContext game={game}/>}
    <section className="panel"><div className="eyebrow">12 REQUIRED INTELLIGENCE DOMAINS</div><h2>Model inputs and research gaps.</h2><p>“Used by the incumbent” means an input affects upcoming probabilities. Research inputs belong to a separate, unpromoted historical challenger. This inventory describes the archived research training dataset. Current player and team annotations above can be available even when a training input is unavailable. None of the expanded research inputs changes this matchup.</p>{research.error?<div role="alert"><p>{research.error}</p><button className="current-reload" onClick={research.retry}>Retry domain inventory</button></div>:!research.data?<p role="status">Loading verified domain inventory…</p>:<div className="domain-grid">{research.data.data.domains.map(d=><DomainCard key={d.id} domain={d}/>)}</div>}</section>
    <section className="panel intelligence-empty"><h2>Weather, news and remaining gaps</h2><p>Game-time weather, verified team developments, individual quarterback performance and confirmed starters remain unavailable. Observed injury and depth-chart annotations above do not adjust model probabilities. No player or team mental state is inferred.</p></section>
    {record && <p><a href={`${import.meta.env.BASE_URL}data/current/${record.artifact_file}`} download>Original matchup forecast JSON</a> · Generated {time(record.generated_at)}</p>}
    <Provenance label="Latest forecast decision artifact" directory="current" file={file} hash={sha256} generated={data.generated_at} retry={()=>{current.retry();operations.retry();}}/>
  </>;
}
function DomainCard({domain:d}:{domain:Domain}) {
  return <article className="domain-card"><span className={`intelligence-tag${d.incumbent_used?"":" unavailable"}`}>{d.incumbent_used?"USED BY INCUMBENT":d.challenger_used?"RESEARCH CHALLENGER ONLY":"NOT TRAINED · NOT USED"}</span><h3>{d.name}</h3><p>Research feature definition: {d.transformation}</p><details><summary>Source, availability and evidence</summary><dl><dt>Training status</dt><dd>{d.status}</dd><dt>Data source</dt><dd><a href={d.source.url} target="_blank" rel="noreferrer">{d.source.name}</a><br/>{d.source.license}<br/>{d.source.historical_availability}</dd><dt>Time boundary</dt><dd>{d.prediction_time_rule}</dd><dt>Research missing inputs</dt><dd>{d.missing_behavior}</dd><dt>Leakage control</dt><dd>{d.leakage_test}</dd><dt>Measured contribution</dt><dd>{d.contribution?<>Full − ablated Brier: {d.contribution.full_minus_ablated_brier.toFixed(4)}; 95% season-week interval [{d.contribution.uncertainty.low.toFixed(4)}, {d.contribution.uncertainty.high.toFixed(4)}]. {d.contribution.n} retrospective games. Negative favors inclusion; correlated-feature comparison, not a causal effect.</>:"Not measured. No contribution is claimed."}</dd></dl></details></article>;
}
