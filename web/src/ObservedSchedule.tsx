import { useState } from "react";
import { loadOperations } from "./operations-contracts";
import { useArtifact } from "./use-artifact";
import { Table, time } from "./IntelligenceShared";

/** Operational status is an observed source fact, never inferred from a clock alone. */
export function ObservedSchedule({ initialWeek }: {initialWeek:number|null}) {
  const evidence=useArtifact(loadOperations);
  const [selected,setSelected]=useState(initialWeek??1);
  return <section className="panel observed-schedule"><div className="eyebrow">CURRENT-SEASON SCHEDULE</div><h2>Observed game status</h2><p>Scheduled, postponed, canceled, in-progress and completed states come from the verified source snapshot. A passed kickoff alone does not confirm a final result.</p>{evidence.error?<div role="status"><p>{evidence.error} Upcoming forecast integrity is checked independently.</p><button className="current-reload" onClick={evidence.retry}>Retry schedule status</button></div>:!evidence.data?<p role="status">Checking observed schedule…</p>:<><p className="muted">Source retrieved {time(evidence.data.data.source.retrieved_at)}. This is a dated snapshot; refresh for later status changes.</p><label className="intelligence-select">Schedule week <select value={selected} onChange={e=>setSelected(Number(e.target.value))}>{Array.from({length:18},(_,i)=><option key={i+1} value={i+1}>Week {i+1}</option>)}</select></label><Table label={`Observed Week ${selected} schedule`}><thead><tr><th>Matchup</th><th>Kickoff</th><th>Venue</th><th>Observed status</th></tr></thead><tbody>{evidence.data.data.schedule.filter(g=>g.week===selected).sort((a,b)=>(a.kickoff??"z").localeCompare(b.kickoff??"z")).map(g=><tr key={g.id}><th>{g.away} at {g.home}</th><td>{time(g.kickoff)}</td><td>{g.stadium}</td><td><span className="intelligence-tag">{g.status.replaceAll("_"," ")}</span></td></tr>)}</tbody></Table></>}</section>;
}
