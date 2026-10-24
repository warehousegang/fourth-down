// Local captured evidence and synthetic outcomes for tests only. Never imported by application code.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { operationsSchema, type Operations } from "./operations-contracts";
import { researchSchema } from "./research-contracts";
import { contextSchema } from "./context-contracts";
function read(directory:string){const root=resolve(`public/data/${directory}`);const pointer=JSON.parse(readFileSync(resolve(root,"latest.json"),"utf8"));const text=readFileSync(resolve(root,pointer.file),"utf8");return {pointer,text};}
export const operationsCapture=read("operations");
export const researchCapture=read("research");
export const contextCapture=read("context");
export const contextFixture=()=>contextSchema.parse(JSON.parse(contextCapture.text));
export const operationsFixture=()=>operationsSchema.parse(JSON.parse(operationsCapture.text));
export const researchFixture=()=>researchSchema.parse(JSON.parse(researchCapture.text));
export function completedFixture():Operations {
  const data=operationsFixture();
  const game=data.games[0];
  data.games=[game];
  data.catalog=data.catalog.filter(f=>f.game_id===game.id);
  data.generated_at=new Date(Date.parse(game.kickoff!)+4*3600000).toISOString();
  game.status="completed";
  data.schedule.find(g=>g.id===game.id)!.status="completed";
  game.final_forecast_id=game.latest_forecast_id;
  game.result={version:"synthetic-test-result",home_score:24,away_score:17,tie:false,observed_at:data.generated_at,source_url:data.source.source_url,snapshot_sha256:data.source.snapshot_sha256};
  const scored=(p:number)=>({correct:p>=.5,brier:(p-1)**2,log_loss:-Math.log(p)});
  game.evaluations=data.catalog.filter(f=>f.eligible).map(f=>{
    f.selected_final=f.id===game.final_forecast_id;
    return {forecast_id:f.id,primary:f.selected_final,home_probability:f.home_probability!,outcome_home:1 as const,...scored(f.home_probability!),surprise:-Math.log(f.home_probability!),baseline:{coin_flip:scored(.5),home_rate:{probability:.5572154167911563,...scored(.5572154167911563)}}};
  });
  game.analysis={facts:[{text:"Synthetic test fixture: final score is 24–17.",source_url:data.source.source_url,observed_at:data.generated_at}],hypotheses:[{text:"Missing quarterback information may warrant investigation.",evidence_needed:"Verified timestamped quarterback availability evidence; no causal claim."}],deficiencies:["The frozen feature set does not include quarterback availability."]};
  const mean=(v:number[])=>v.reduce((a,b)=>a+b,0)/v.length;
  const aggregate=(rows:{correct:boolean;brier:number;log_loss:number}[])=>({count:rows.length,accuracy:mean(rows.map(e=>Number(e.correct))),brier:mean(rows.map(e=>e.brier)),log_loss:mean(rows.map(e=>e.log_loss))});
  for(const key of ["primary","all_snapshots"] as const){
    const rows=game.evaluations.filter(e=>key==="all_snapshots"||e.primary);
    const m=data.metrics[key];Object.assign(m,aggregate(rows),{game_count:1,ties_excluded:0});
    m.baselines={coin_flip:aggregate(rows.map(e=>e.baseline.coin_flip)),home_rate:aggregate(rows.map(e=>e.baseline.home_rate))};
    m.by_season=[{season:data.season,...aggregate(rows)}];
    m.calibration=m.calibration.map(b=>{const inBin=rows.filter(e=>e.home_probability>=b.lower&&e.home_probability<b.upper);return {...b,count:inBin.length,mean_probability:inBin.length?mean(inBin.map(e=>e.home_probability)):null,home_win_rate:inBin.length?1:null,brier:inBin.length?mean(inBin.map(e=>e.brier)):null};});
  }
  return operationsSchema.parse(data);
}
