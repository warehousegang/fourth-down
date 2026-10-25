import { ArrowRight, RefreshCw } from "lucide-react";
import { loadCurrent } from "./current-contracts";
import { loadOperations } from "./operations-contracts";
import { useArtifact } from "./use-artifact";
import { selectDisplayForecast, displayRecord, displayGames } from "./forecast-display";
import { ForecastOutcome, gameStatus } from "./ForecastOutcome";
import { PredictionScoreboard } from "./PredictionScoreboard";
import { PredictionDetails } from "./PredictionDetails";
import { team } from "./teams";
import { TeamMark } from "./TeamMark";
import { ObservedSchedule } from "./ObservedSchedule";
import { useForecastClock } from "./use-forecast-clock";

const time = (s: string | null) => s ? new Intl.DateTimeFormat("en-US", { month:"short", day:"numeric", year:"numeric", hour:"numeric", minute:"2-digit", timeZone:"America/New_York", timeZoneName:"short" }).format(new Date(s)) : "Kickoff unconfirmed";
const pct = (p: number) => `${(p*100).toFixed(1)}%`;

export function CurrentForecasts() {
  const operations = useArtifact(loadOperations,60_000);
  const current = useArtifact(loadCurrent,60_000);
  const loaded=current.data;
  const now=useForecastClock(loaded?[loaded.data.valid_until,...loaded.data.games.map(g=>g.kickoff)]:[]);
  if (!loaded && current.error) return <section className="empty-state" role="alert"><h1>Current forecasts unavailable</h1><p>{current.error}</p><p>Historical analysis remains available in the navigation.</p><button onClick={current.retry}>Retry artifact load</button></section>;
  if (!loaded) return <section className="empty-state" role="status"><h1>Loading Current Week Forecasts</h1><p>Verifying the snapshot and frozen model…</p></section>;
  const { data } = loaded;
  const candidate = operations.data?.data;
  const evidence = candidate && Date.parse(candidate.generated_at)<=now ? candidate : null;
  const games = displayGames(data,evidence,now);
  const recentWeek=Math.max(0,...games.filter(g=>g.kickoff&&Date.parse(g.kickoff)<=now).map(g=>g.week));
  const week=recentWeek||data.week;
  return <>
    <section className="page-heading hero-heading current-heading">
      <div><div className="eyebrow">// {data.season} NFL · PREGAME PICKS & VERIFIED RESULTS</div>
        <h1><span className="hero-intro">NFL predictions.</span><span>From kickoff to final.</span></h1>
        <h2>Current Week Forecasts</h2><p>See the pick, follow the result, and track the record.<br/>Every prediction stays fixed once the game begins.</p></div>
    </section>
    <PredictionScoreboard operations={evidence} week={week} checkedAt={operations.checkedAt} error={operations.error??undefined}/>
    <p className="game-day-note">Pregame predictions use the inputs available when saved. Injuries, weather, and breaking news are not included. Results appear only after verification.</p>
    {operations.error && <p className="current-warning" role="alert">Forecast provenance unavailable: {operations.error} {evidence?"Showing the last verified saved evidence.":"Predictions will return when their saved evidence can be verified."}</p>}
    {!games.length && <section className="panel"><h2>No current matchups</h2><p>Saved predictions remain available in Forecast History. No matchups or results are invented.</p></section>}
    <div className="current-grid">
      {games.map(g => {
        const choice = selectDisplayForecast(data,g,evidence,now);
        const record = displayRecord(evidence,choice);
        const view = record ?? ("cutoff" in g ? g : null);
        const reason = choice.reason;
        const status=gameStatus(g,evidence,now);
        const predicted=record&&record.home_probability!==null?team(record.home_probability>=.5?g.home:g.away).name:null;
        return <article key={g.id} className={`panel current-card game-day-card${status==="Final"?" game-final":""}`} aria-label={`${team(g.away).name} at ${team(g.home).name} current forecast`}>
          <div className="current-card-top"><span>WEEK {g.week}</span><span className={`game-status status-${status.toLowerCase().replaceAll(" ","-")}`}>{status}</span></div>
          <p className="game-kickoff">Kickoff <time dateTime={g.kickoff??undefined}>{time(g.kickoff)}</time></p>
          <div className="current-teams"><div><TeamMark code={g.away} size="current"/><h3>{team(g.away).name}</h3><small>{g.away} · AWAY</small></div><span className="current-at">at</span><div><TeamMark code={g.home} size="current"/><h3>{team(g.home).name}</h3><small>{g.home} · HOME</small></div></div>
          {reason || !record ? <div className="current-unavailable"><strong>Prediction unavailable</strong><p>No eligible, verified pregame prediction is available for this matchup. See Prediction details for the reason.</p></div> : <>
            <div className="prediction-label">Pregame prediction</div>
            <div className="current-probabilities"><div><span>{g.away}</span><strong>{pct(record.away_probability!)}</strong><strong>{pct(record.home_probability!)}</strong><span>{g.home}</span></div><div className="current-probability-bar" aria-hidden="true"><span style={{width:pct(record.away_probability!)}}/></div></div>
            <p className="predicted-winner">Predicted winner <strong>{predicted}</strong></p>
          </>}
          {record && <p className="current-cutoff">Prediction saved <time dateTime={record.generated_at} title={record.generated_at}>{time(record.generated_at)}</time></p>}
          <ForecastOutcome game={g} operations={evidence} record={record} now={now}/>
          <div className="current-card-actions"><a className="current-intelligence-link" href={`#intelligence?game=${encodeURIComponent(g.id)}`}>Explore matchup intelligence <ArrowRight size={14} aria-hidden="true"/></a>{reason&&<a href="#history">Inspect retained forecast history</a>}{record&&<a className="current-data-link" href={`${import.meta.env.BASE_URL}data/current/${record.artifact_file}`} download>View prediction data (JSON)</a>}</div>
          <PredictionDetails record={view} current={data} reason={reason}/>
        </article>;
      })}
    </div>
    <ObservedSchedule initialWeek={data.week}/>
    <details className="panel current-limitations"><summary>Model limitations and research context</summary><ul>{data.limitations.map(l=><li key={l}>{l}</li>)}</ul><p>The 2024–2025 assessment remains locked and partially exposed. This screen does not evaluate those seasons or imply new accuracy evidence.</p><a href="#performance">View the separate 2023 validation <ArrowRight size={15}/></a></details>
    <footer className="current-footer"><span>FOURTH DOWN / Saved predictions · Verified results</span><span>Schedule: <a href={data.source.source_url} target="_blank" rel="noreferrer">SportsDataverse / NFL Next Gen Stats</a> · Results: <a href="https://github.com/nflverse/nflverse-pbp">nflverse</a> · <a href={`${import.meta.env.BASE_URL}CURRENT_DATA_NOTICE.txt`}>Data attribution and license</a></span><p>Model {data.model.id} · No affiliation with the NFL. Educational research, not betting advice.</p><details><summary>Published data and source provenance</summary><p>Latest decision: {time(data.generated_at)}<br/>Source published: {time(data.source.source_updated_at)}<br/>Source observed: {time(data.source.retrieved_at)}<br/>Forecast SHA256: {loaded.sha256}<br/>Source SHA256: {data.source.raw_sha256}<br/>Snapshot SHA256: {data.snapshot_sha256}</p><a href={`${import.meta.env.BASE_URL}data/current/${loaded.file}`} download>Download this forecast JSON</a></details><a href={`${import.meta.env.BASE_URL}THIRD_PARTY_NOTICES.txt`}>Third-party dependency notices</a><button className="current-reload" onClick={()=>{current.retry(); operations.retry();}}><RefreshCw size={14}/> Check published updates</button></footer>
  </>;
}
