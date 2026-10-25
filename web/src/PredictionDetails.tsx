import type { CurrentArtifact, CurrentGame } from "./current-contracts";
import type { ForecastRecord } from "./operations-contracts";
import { time } from "./IntelligenceShared";

export function PredictionDetails({record,current,reason}:{record:ForecastRecord|CurrentGame|null;current:CurrentArtifact;reason:string|null}) {
  const source=record&&"source" in record?record.source:current.source;
  return <details className="current-inputs prediction-details"><summary>Prediction details</summary>
    <dl className="prediction-provenance"><dt>Model version</dt><dd>{record?.model_id??current.model.id}</dd><dt>Original forecast</dt><dd>{record?time(record.generated_at):"No prediction recorded"}</dd><dt>Data cutoff</dt><dd>{record?time(record.cutoff):"Unavailable"}</dd><dt>Original scheduled kickoff</dt><dd>{record?time(record.kickoff):"Unconfirmed"}</dd><dt>Source published</dt><dd>{time(source.source_updated_at)}</dd><dt>Source observed</dt><dd>{time(source.retrieved_at)}</dd></dl>
    {reason&&<p>Availability check: {reason}</p>}
    <p>These probabilities use the inputs available at the original forecast time. They are not live win probabilities and are never recalculated after kickoff. A later source check does not change this timestamp.</p>
    {record?.factors.length?<><p>Earlier completed games: {record.history.away.length} away · {record.history.home.length} home. Only results observed before the cutoff enter the model.</p><div className="current-feature-table" role="region" aria-label="Saved prediction feature values" tabIndex={0}><table><thead><tr><th>Input</th><th>Away</th><th>Home</th><th>Contribution</th></tr></thead><tbody>{record.factors.map(f=><tr key={f.key}><th>{f.label}</th><td>{f.away.toFixed(3)}</td><td>{f.home.toFixed(3)}</td><td>{f.contribution.toFixed(4)}</td></tr>)}</tbody></table></div></>:<p>No verified feature values are available for this prediction.</p>}
    <p>Missing inputs: injuries, confirmed starting quarterbacks, weather, and breaking news do not adjust this model. Probabilities are conditional on no tie and are not guarantees. Feature contributions are associations, not causal explanations.</p>
    <p>Source SHA256: <code>{source.raw_sha256}</code></p><a href={current.source.source_url} target="_blank" rel="noreferrer">Schedule source and provenance</a>
  </details>;
}
