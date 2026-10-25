import type { DisplayGame } from "./forecast-display";
import type { ForecastRecord, Operations } from "./operations-contracts";
import { time } from "./IntelligenceShared";
import { team } from "./teams";

/** Outcomes come only from verified operations, never from elapsed game time. */
export function ForecastOutcome({game, operations, record, now}: {game:DisplayGame; operations:Operations|null; record:ForecastRecord|null; now:number}) {
  if (!operations || Date.parse(operations.generated_at)>now || operations.season!==game.season) return null;
  const observed=operations.games.find(g=>g.id===game.id && g.home===game.home && g.away===game.away && g.kickoff===game.kickoff && g.week===game.week);
  if (!observed) return null;
  if (!observed.result) {
    const message=observed.status==="postponed" ? "Postponed · awaiting confirmed schedule."
      : observed.status==="canceled" ? "Canceled · no result to score."
      : observed.status==="in_progress" ? "In progress · awaiting verified final result."
      : game.kickoff && now>=Date.parse(game.kickoff) ? "Kickoff passed · awaiting verified game status and final result." : null;
    return message ? <p className="current-context" role="status">{message}</p> : null;
  }
  const result=observed.result;
  const evaluation=observed.evaluations.find(e=>e.primary && e.forecast_id===observed.final_forecast_id && e.forecast_id===record?.id);
  return <div className="current-outcome">
    <p><strong>Verified final: {game.away} {result.away_score} · {game.home} {result.home_score}</strong><br/>{result.tie ? "Result: tie" : `Actual winner: ${team(result.home_score>result.away_score ? game.home : game.away).name}`}</p>
    {evaluation ? <p>Pregame pick: {evaluation.correct ? "Correct" : "Incorrect"} · Brier: {evaluation.brier.toFixed(4)} · Log loss: {evaluation.log_loss.toFixed(4)} nats</p>
      : <p>{result.tie ? "Tie excluded from binary scoring." : "No verified designated forecast score is available."}</p>}
    <p className="small"><a href={result.source_url} target="_blank" rel="noreferrer">Result source</a> · Observed {time(result.observed_at)}. Later verified corrections appear in a new evaluation version.</p>
  </div>;
}
