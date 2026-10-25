import { useState } from "react";
import type { Operations } from "./operations-contracts";
import { time } from "./IntelligenceShared";

/** Summarize only the already validated primary evaluation, once per game. */
export function predictionPerformance(operations:Operations, week?:number) {
  const games=operations.games.filter(g=>week===undefined||g.week===week);
  const eligible=new Set(operations.catalog.filter(f=>f.eligible).map(f=>f.game_id));
  const scored=games.flatMap(g=>g.result&&!g.result.tie&&g.status==="completed"
    ?g.evaluations.filter(e=>e.primary&&e.forecast_id===g.final_forecast_id):[]);
  const correct=scored.filter(e=>e.correct).length;
  const pending=games.filter(g=>eligible.has(g.id)&&!g.result&&!["canceled","postponed"].includes(g.status)).length;
  const mean=(values:number[])=>values.length?values.reduce((a,b)=>a+b,0)/values.length:null;
  const updates=games.flatMap(g=>g.result?[g.result.observed_at]:[]).sort((a,b)=>Date.parse(a)-Date.parse(b));
  return {count:scored.length,correct,incorrect:scored.length-correct,pending,
    excluded:games.length-scored.length-pending,accuracy:scored.length?correct/scored.length:null,
    brier:mean(scored.map(e=>e.brier)),logLoss:mean(scored.map(e=>e.log_loss)),lastVerified:updates.at(-1)??null};
}

export function PredictionScoreboard({operations,week,error,checkedAt}:{operations:Operations|null;week:number|null;error?:string;checkedAt?:string|null}) {
  const [scope,setScope]=useState<"week"|"season">("week");
  const stats=operations?predictionPerformance(operations,scope==="week"?week??undefined:undefined):null;
  const percent=stats?.accuracy===null||stats?.accuracy===undefined?"—":`${(stats.accuracy*100).toFixed(1)}%`;
  return <section className="panel prediction-scoreboard" aria-labelledby="prediction-scoreboard-title">
    <div className="scoreboard-heading"><div><div className="eyebrow">SAVED PICKS · VERIFIED RESULTS</div><h2 id="prediction-scoreboard-title">Prediction Scoreboard</h2><p>{scope==="week"&&week?`Week ${week}`:`${operations?.season??"Season"} to date`} — Prediction Performance</p></div>
      <div className="scoreboard-scope" role="group" aria-label="Performance period"><button aria-pressed={scope==="week"} onClick={()=>setScope("week")}>Current week</button><button aria-pressed={scope==="season"} onClick={()=>setScope("season")}>Season to date</button></div></div>
    {!stats?<p role={error?"alert":"status"}>{error?"Verified performance is temporarily unavailable. Predictions are never scored without their evidence.":"Loading verified forecast history…"}</p>:<>
      <dl className="scoreboard-primary"><div><dt>Accuracy</dt><dd>{percent}</dd></div><div><dt>Games scored</dt><dd>{stats.count}</dd></div><div><dt>Correct</dt><dd>{stats.correct}<small> / {stats.count}</small></dd></div><div><dt>Incorrect</dt><dd>{stats.incorrect}</dd></div><div><dt>Pending</dt><dd>{stats.pending}</dd></div></dl>
      <div className="scoreboard-secondary"><p><span>Brier score</span><strong>{stats.brier?.toFixed(4)??"—"}</strong></p><p><span>Log loss</span><strong>{stats.logLoss?.toFixed(4)??"—"}<small> nats</small></strong></p><p><span>Last verified results update</span><strong>{stats.lastVerified?<time dateTime={stats.lastVerified}>{time(stats.lastVerified)}</time>:"Awaiting the first verified final"}</strong></p></div>
      <div className="scoreboard-secondary scoreboard-freshness"><p><span>Results last checked</span><strong>{checkedAt?<time dateTime={checkedAt}>{time(checkedAt)}</time>:"Not checked in this tab"}</strong></p><p><span>Result provider last published</span><strong>{operations?.result_feed?<time dateTime={operations.result_feed.source_updated_at}>{time(operations.result_feed.source_updated_at)}</time>:"No supplemental result received"}</strong></p></div>
      <p className="scoreboard-note">This tab checks published results every minute while visible. The check time confirms a successful dashboard fetch; provider publication and verified result times can be earlier.</p>
      {!stats.count&&<p className="scoreboard-note">No games scored yet. Accuracy and scoring metrics appear when an eligible saved prediction has a verified, non-tied final result.</p>}
      <details className="scoreboard-method"><summary>How performance is measured</summary><p>One designated pregame prediction per game. Pending games, ties, canceled or postponed games, and games without an eligible prediction do not count toward accuracy. {stats.excluded} game{stats.excluded===1?" is":"s are"} currently outside this scoring sample.</p><p>Brier score and log loss measure the quality of the saved probabilities; lower is better. This is prospective V1 performance for {operations?.season}, separate from historical validation, simulations, and V2 research.</p><a href="#postgame">Explore verified postgame analysis</a></details>
    </>}
  </section>;
}
