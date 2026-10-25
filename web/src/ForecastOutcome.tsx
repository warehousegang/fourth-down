import type { DisplayGame } from "./forecast-display";
import type { ForecastRecord, Operations } from "./operations-contracts";
import { time } from "./IntelligenceShared";
import { team } from "./teams";

export function gameStatus(game:DisplayGame, operations:Operations|null, now:number) {
  const observed=operations?.games.find(g=>g.id===game.id&&g.home===game.home&&g.away===game.away&&g.kickoff===game.kickoff);
  const state=observed?.status??("status" in game?game.status:"unknown");
  if(state==="completed"&&observed?.result)return "Final";
  if(state==="in_progress")return "In progress";
  if(state==="postponed")return "Postponed";
  if(state==="canceled")return "Canceled";
  return game.kickoff&&now<Date.parse(game.kickoff)?"Upcoming":"Awaiting result update";
}

/** Outcomes come only from verified operations, never from elapsed game time. */
export function ForecastOutcome({game, operations, record, now}: {game:DisplayGame; operations:Operations|null; record:ForecastRecord|null; now:number}) {
  if (!operations || Date.parse(operations.generated_at)>now || operations.season!==game.season) return null;
  const observed=operations.games.find(g=>g.id===game.id && g.home===game.home && g.away===game.away && g.kickoff===game.kickoff && g.week===game.week);
  if (!observed) return null;
  if (!observed.result) {
    const message=observed.status==="postponed" ? "Awaiting a confirmed schedule. The saved prediction is preserved and excluded from scoring."
      : observed.status==="canceled" ? "The saved prediction is preserved. This game is not scored."
      : observed.status==="in_progress" ? "Awaiting a verified final score. The pregame prediction stays fixed."
      : game.kickoff && now>=Date.parse(game.kickoff) ? "Awaiting a verified game update. No score or result has been assumed." : null;
    return message ? <p className="current-context" role="status">{message}</p> : null;
  }
  const result=observed.result;
  const evaluation=observed.evaluations.find(e=>e.primary && e.forecast_id===observed.final_forecast_id && e.forecast_id===record?.id);
  return <div className={`current-outcome ${evaluation?(evaluation.correct?"outcome-correct":"outcome-incorrect"):"outcome-unscored"}`}>
    <div className="outcome-heading"><span>FINAL SCORE</span><strong>{evaluation?(evaluation.correct?"Correct prediction":"Incorrect prediction"):result.tie?"Tie · not scored":"Not scored"}</strong></div>
    <p className="final-score" aria-label={`Verified final: ${game.away} ${result.away_score} · ${game.home} ${result.home_score}`}><span>{game.away} <strong>{result.away_score}</strong></span><span>{game.home} <strong>{result.home_score}</strong></span></p>
    <p>{result.tie ? "Result: tie" : `Actual winner: ${team(result.home_score>result.away_score ? game.home : game.away).name}`}</p>
    {evaluation ? <p className="outcome-metrics">Brier: {evaluation.brier.toFixed(4)} · Log loss: {evaluation.log_loss.toFixed(4)} nats</p>
      : <p>{result.tie ? "Tie excluded from binary scoring." : "No verified designated forecast score is available."}</p>}
    <details className="outcome-evidence"><summary>Verified result source</summary><p className="small"><a href={result.source_url} target="_blank" rel="noreferrer">Result source</a> · Observed {time(result.observed_at)}. Later verified corrections appear in a new evaluation version.</p></details>
  </div>;
}
