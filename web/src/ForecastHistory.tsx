import { useState } from "react";
import { ArrowRight, History } from "lucide-react";
import { loadOperations, type ForecastRecord } from "./operations-contracts";
import { useArtifact } from "./use-artifact";
import { Heading, LoadState, pct, Provenance, signed, Table, time } from "./IntelligenceShared";
import { team } from "./teams";

export function ForecastHistory() {
  const evidence = useArtifact(loadOperations);
  const [selection, setSelection] = useState("");
  if (!evidence.data) return <LoadState title="Forecast History" error={evidence.error} retry={evidence.retry}/>;
  const { data, file, sha256 } = evidence.data;
  const game = data.games.find(g=>g.id===selection) ?? data.games[0];
  const map = new Map(data.catalog.map(f=>[f.id,f]));
  const records = game ? game.forecast_ids.map(id=>map.get(id)!).sort((a,b)=>a.generated_at.localeCompare(b.generated_at) || a.id.localeCompare(b.id)) : [];
  const original = game?.original_forecast_id ? map.get(game.original_forecast_id) : undefined;
  const latest = game?.latest_forecast_id ? map.get(game.latest_forecast_id) : undefined;
  const final = game?.final_forecast_id ? map.get(game.final_forecast_id) : undefined;
  const delta = original?.home === latest?.home && original?.away === latest?.away && original?.home_probability !== null && original?.home_probability !== undefined && latest?.home_probability !== null && latest?.home_probability !== undefined ? (latest.home_probability-original.home_probability)*100 : null;
  return <>
    <Heading label="IMMUTABLE FORECAST LEDGER" title="Forecast History">Every version keeps its inputs, cutoff and checksum. Updated probabilities never replace the record of an earlier forecast.</Heading>
    <div className="intelligence-summary panel"><History size={24}/><div><strong>{data.catalog.length} forecast records · {data.games.length} matchups</strong><p>Archived probabilities describe what was known at that timestamp. They remain visible after current-forecast freshness expires.</p></div></div>
    {data.warnings.map(w=><p key={w} className="current-warning">{w}</p>)}
    {!game ? <section className="panel"><h2>No recorded forecasts</h2><p>A successful local refresh creates the first immutable record.</p></section> : <>
      <label className="intelligence-select">Matchup <select value={game.id} onChange={e=>setSelection(e.target.value)}>{data.games.map(g=><option key={g.id} value={g.id}>Week {g.week} · {g.away} at {g.home} · {g.status.replaceAll("_"," ")}</option>)}</select></label>
      <section className="panel history-comparison"><div className="eyebrow">{game.id} · {game.status.replaceAll("_", " ")}</div><h2>{team(game.away).name} at {team(game.home).name}</h2><p>Kickoff: {time(game.kickoff)}. Each version names its recorded home team. Probabilities are conditional on no tie; schedule corrections can exclude an earlier version.</p><div className="history-summary-grid"><ForecastLabel title="Original record" record={original}/><ForecastLabel title="Latest record" record={latest}/><div><span className="eyebrow">Change from original</span><strong>{delta===null ? "Unavailable" : `${signed(delta)} pp`}</strong><p>Percentage points · same frozen model</p></div><ForecastLabel title="Final pregame record" record={final} fallback="Not designated before kickoff"/></div></section>
      <section className="panel"><h2>Version timeline</h2><p>Final designation occurs after the observed kickoff and uses the last eligible pregame record. Later result updates cannot change its probability.</p><ol className="forecast-timeline">{records.map(record=><li key={record.id}><div className="timeline-dot"/><div><div className="timeline-title"><h3>{time(record.generated_at)}</h3><span className="intelligence-tag">{record.selected_final ? "FINAL PREGAME" : record.latest ? "LATEST RECORD" : "ARCHIVED"}</span></div><p>{record.home} win: <strong>{pct(record.home_probability)}</strong> · Cutoff {time(record.cutoff)}</p><p className="muted">{record.eligible ? "Eligible pregame forecast" : `Excluded: ${record.exclusions.join("; ")}`} · Display validity ended {time(record.valid_until)}</p><details><summary>Inputs and provenance <ArrowRight size={14}/></summary><Table label={`${record.id} frozen input snapshot`}><thead><tr><th>Input</th><th>Away</th><th>Home</th><th>Contribution</th></tr></thead><tbody>{record.factors.map(f=><tr key={f.key}><th>{f.label}</th><td>{f.away.toFixed(4)}</td><td>{f.home.toFixed(4)}</td><td>{f.contribution.toFixed(4)}</td></tr>)}</tbody></Table><p>Model {record.model_id}. Earlier completed games: {record.away} {record.history.away.length} · {record.home} {record.history.home.length}.</p><p className="intelligence-hash">Forecast record: {record.id}<br/>Artifact SHA256: {record.artifact_sha256}</p><a href={`${import.meta.env.BASE_URL}data/current/${record.artifact_file}`} download>Download original forecast artifact</a></details></div></li>)}</ol></section>
    </>}
    <Provenance label="Forecast archive index" directory="operations" file={file} hash={sha256} generated={data.generated_at} retry={evidence.retry}/>
  </>;
}
function ForecastLabel({ title, record, fallback = "Unavailable" }: {title:string;record?:ForecastRecord;fallback?:string}) {
  return <div><span className="eyebrow">{title}</span><strong>{record ? record.home_probability === null ? "Unavailable" : `${record.home} ${pct(record.home_probability)}` : "Pending"}</strong><p>{record ? time(record.generated_at) : fallback}</p></div>;
}
