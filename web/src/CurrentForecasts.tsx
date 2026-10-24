import { useEffect, useState } from "react";
import { ArrowRight, Clock3, Database, RefreshCw, ShieldCheck } from "lucide-react";
import { loadCurrent, unavailableReason, type LoadedCurrent } from "./current-contracts";
import { team } from "./teams";
import { TeamMark } from "./TeamMark";
import { ObservedSchedule } from "./ObservedSchedule";
import { useForecastClock } from "./use-forecast-clock";

const time = (s: string | null) => s ? new Intl.DateTimeFormat("en-US", { month:"short", day:"numeric", year:"numeric", hour:"numeric", minute:"2-digit", timeZone:"America/New_York", timeZoneName:"short" }).format(new Date(s)) : "Kickoff unconfirmed";
const pct = (p: number) => `${(p*100).toFixed(1)}%`;

export function CurrentForecasts() {
  const [loaded, setLoaded] = useState<LoadedCurrent | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const now = useForecastClock(loaded ? [loaded.data.valid_until, ...loaded.data.games.map(g=>g.kickoff)] : []);
  useEffect(() => {
    let active = true;
    setError(""); setLoaded(null);
    loadCurrent().then(value => { if (active) setLoaded(value); }).catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [attempt]);
  if (error) return <section className="empty-state" role="alert"><h1>Current forecasts unavailable</h1><p>{error}</p><p>Historical analysis remains available in the navigation.</p><button onClick={() => setAttempt(n => n+1)}>Retry artifact load</button></section>;
  if (!loaded) return <section className="empty-state" role="status"><h1>Loading Current Week Forecasts</h1><p>Verifying the snapshot and frozen model…</p></section>;
  const { data } = loaded;
  const available = data.games.filter(g => !unavailableReason(data,g,now)).length;
  const expired = now >= Date.parse(data.valid_until);
  return <>
    <section className="page-heading hero-heading current-heading">
      <div><div className="eyebrow">// {data.season} NFL · {data.week ? `WEEK ${String(data.week).padStart(2,"0")}` : "NO UPCOMING WEEK"}</div>
        <h1><span className="hero-intro">Next up.</span><span>Before the kickoff.</span></h1>
        <h2>Current Week Forecasts</h2><p>Upcoming games. The original frozen model.<br/>A dated snapshot of what the model knows.</p></div>
    </section>
    <section className="current-provenance panel" aria-label="Current forecast provenance">
      <div><span className="eyebrow"><Clock3 size={14}/> DECISION TIME</span><strong>{time(data.as_of)}</strong></div>
      <div><span className="eyebrow"><Database size={14}/> SOURCE UPDATED</span><strong>{time(data.source.source_updated_at)}</strong></div>
      <div><span className="eyebrow"><ShieldCheck size={14}/> AVAILABLE FORECASTS</span><strong>{available} / {data.games.length}</strong></div>
      <p>Generated {time(data.generated_at)} · Source retrieved {time(data.source.retrieved_at)}.<br/>Manual snapshot. Refresh is required after {time(data.valid_until)} or when the schedule changes.</p>
    </section>
    {expired && <div className="current-warning" role="status"><strong>Snapshot expired — probabilities hidden.</strong> Run a local refresh to obtain a new version.</div>}
    {data.warnings.map(w => <p className="current-warning" key={w}>{w}</p>)}
    <p className="current-context">Current-season inputs only: season win rate, scoring margin, recent margin and rest. No injury, player-news, weather or prior-season strength adjustment. Probabilities are conditional on no tie.</p>
    {!data.games.length && <section className="panel"><h2>No upcoming regular-season games</h2><p>No matchups are invented. Refresh when a confirmed schedule is available.</p></section>}
    <div className="current-grid">
      {data.games.map(g => {
        const reason = unavailableReason(data,g,now);
        return <article key={g.id} className="panel current-card" aria-label={`${team(g.away).name} at ${team(g.home).name} current forecast`}>
          <div className="current-card-top"><span>WEEK {g.week}</span><span>{time(g.kickoff)}</span></div>
          <div className="current-teams"><div><TeamMark code={g.away} size="current"/><h3>{team(g.away).name}</h3><small>{g.away} · AWAY</small></div><span className="current-at">at</span><div><TeamMark code={g.home} size="current"/><h3>{team(g.home).name}</h3><small>{g.home} · HOME</small></div></div>
          <p className="muted current-venue">{g.stadium}</p>
          {reason ? <div className="current-unavailable"><strong>Prediction unavailable</strong><p>{reason}</p></div> : <div className="current-probabilities"><div><span>{g.away}</span><strong>{pct(g.away_probability!)}</strong><strong>{pct(g.home_probability!)}</strong><span>{g.home}</span></div><div className="current-probability-bar" aria-hidden="true"><span style={{width:pct(g.away_probability!)}}/></div><small>MODEL ESTIMATE · NOT A GUARANTEE</small></div>}
          {g.warnings.map(w => <p className="current-warning small" key={w}>{w}</p>)}
          <p className="current-cutoff">Data cutoff: {time(g.cutoff)}<br/>Matchup: {g.id}</p>
          <a className="current-intelligence-link" href={`#intelligence?game=${encodeURIComponent(g.id)}`}>Explore matchup intelligence <ArrowRight size={14}/></a>
          {!reason && <details className="current-inputs"><summary>Inspect the four model inputs <ArrowRight size={14}/></summary><p>Earlier completed games: {g.away} {g.history.away.length} · {g.home} {g.history.home.length}. Results must be observed as final before this cutoff; same-day games are excluded.</p><div className="current-feature-table" role="region" aria-label={`${g.away} at ${g.home} feature values`} tabIndex={0}><table><thead><tr><th>Input</th><th>{g.away}</th><th>{g.home}</th><th>Contribution</th></tr></thead><tbody>{g.factors.map(f=><tr key={f.key}><th>{f.label}</th><td>{f.away.toFixed(3)}</td><td>{f.home.toFixed(3)}</td><td>{f.contribution.toFixed(4)}</td></tr>)}</tbody></table></div><p>Contribution = coefficient × (home − away), in log-odds. Frozen intercept {data.model.intercept.toFixed(6)}. These associations are not causal explanations.</p></details>}
        </article>;
      })}
    </div>
    <ObservedSchedule initialWeek={data.week}/>
    <section className="panel current-limitations"><div className="eyebrow">READ BEFORE USING</div><h2>What this forecast can tell you</h2><ul>{data.limitations.map(l=><li key={l}>{l}</li>)}</ul><p>The 2024–2025 assessment remains locked and partially exposed. This screen does not evaluate those seasons or imply new accuracy evidence.</p><a href="#performance">View the separate 2023 validation <ArrowRight size={15}/></a></section>
    <footer className="current-footer"><span>FOURTH DOWN / Current forecast snapshot</span><span>Source: <a href={data.source.source_url} target="_blank" rel="noreferrer">SportsDataverse / NFL Next Gen Stats</a> · <a href={`${import.meta.env.BASE_URL}CURRENT_DATA_NOTICE.txt`}>Data attribution and license</a></span><p>Model {data.model.id} · No affiliation with the NFL. Educational research, not betting advice.</p><details><summary>Version and source provenance</summary><p>Forecast SHA256: {loaded.sha256}<br/>Source SHA256: {data.source.raw_sha256}<br/>Snapshot SHA256: {data.snapshot_sha256}</p><a href={`${import.meta.env.BASE_URL}data/current/${loaded.file}`} download>Download this forecast JSON</a></details><a href={`${import.meta.env.BASE_URL}THIRD_PARTY_NOTICES.txt`}>Third-party dependency notices</a><button className="current-reload" onClick={()=>setAttempt(n=>n+1)}><RefreshCw size={14}/> Reload local artifact</button></footer>
  </>;
}
