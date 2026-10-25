// Synthetic results for regression tests only; never imported by application code.
import type { Operations } from "../src/operations-contracts";

export function completedOperations(input:Operations, homeScore=24, awayScore=17):Operations {
  const data=structuredClone(input);
  const game=data.games[0];
  data.games=[game];
  data.catalog=data.catalog.filter(f=>f.game_id===game.id);
  data.generated_at=new Date(Date.parse(game.kickoff!)+4*3600000).toISOString();
  game.status="completed";
  data.schedule.find(g=>g.id===game.id)!.status="completed";
  game.final_forecast_id=data.catalog.filter(f=>f.eligible).at(-1)?.id??null;
  game.result={version:"synthetic-test-result",home_score:homeScore,away_score:awayScore,tie:homeScore===awayScore,observed_at:data.generated_at,source_url:data.source.source_url,snapshot_sha256:data.source.snapshot_sha256};
  const y=homeScore>awayScore?1:0;
  const scored=(p:number)=>({correct:(p>=.5)===Boolean(y),brier:(p-y)**2,log_loss:-Math.log(y?p:1-p)});
  game.evaluations=data.catalog.filter(f=>f.eligible && homeScore!==awayScore).map(f=>{
    f.selected_final=f.id===game.final_forecast_id;
    return {forecast_id:f.id,primary:f.selected_final,home_probability:f.home_probability!,outcome_home:y,...scored(f.home_probability!),surprise:scored(f.home_probability!).log_loss,baseline:{coin_flip:scored(.5),home_rate:{probability:.5572154167911563,...scored(.5572154167911563)}}};
  });
  for(const f of data.catalog)f.selected_final=f.id===game.final_forecast_id;
  game.analysis={facts:[{text:`Synthetic test fixture: final score is ${homeScore}–${awayScore}.`,source_url:data.source.source_url,observed_at:data.generated_at}],hypotheses:[{text:"Missing quarterback information may warrant investigation.",evidence_needed:"Verified timestamped quarterback availability evidence; no causal claim."}],deficiencies:["The frozen feature set does not include quarterback availability."]};
  const mean=(v:number[])=>v.length?v.reduce((a,b)=>a+b,0)/v.length:null;
  const aggregate=(rows:{correct:boolean;brier:number;log_loss:number}[])=>({count:rows.length,accuracy:mean(rows.map(e=>Number(e.correct))),brier:mean(rows.map(e=>e.brier)),log_loss:mean(rows.map(e=>e.log_loss))});
  for(const key of ["primary","all_snapshots"] as const){
    const rows=game.evaluations.filter(e=>key==="all_snapshots"||e.primary);
    const m=data.metrics[key];Object.assign(m,aggregate(rows),{game_count:rows.length?1:0,ties_excluded:homeScore===awayScore?(key==="primary"?1:data.catalog.filter(f=>f.eligible).length):0});
    m.baselines={coin_flip:aggregate(rows.map(e=>e.baseline.coin_flip)),home_rate:aggregate(rows.map(e=>e.baseline.home_rate))};
    m.by_season=rows.length?[{season:data.season,...aggregate(rows)}]:[];
    m.calibration=m.calibration.map(b=>{const inBin=rows.filter(e=>e.home_probability>=b.lower&&e.home_probability<b.upper);return {...b,count:inBin.length,mean_probability:inBin.length?mean(inBin.map(e=>e.home_probability)):null,home_win_rate:inBin.length?y:null,brier:inBin.length?mean(inBin.map(e=>e.brier)):null};});
  }
  return data;
}
