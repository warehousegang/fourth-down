import { z } from "zod";
import frozen from "../../docs/FROZEN_MODEL.json";
import { count, digest, finite, loadVersioned, probability, sourceURL, timestamp } from "./versioned-artifact";
const metric = z.object({n:count.min(1),accuracy:probability,brier:probability,log_loss:finite.nonnegative()});
const calibration = z.array(z.object({bin:count.max(9),count:count.min(1),predicted:probability,observed:probability}));
const uncertainty = z.object({mean:finite,low:finite,high:finite,unit:z.literal("season-week"),stratified_by_season:z.literal(true),replicates:count.min(1),seed:z.number().int()});
const model = z.object({id:z.string().optional(),features:z.array(z.string()).min(1),coefficients:z.array(finite),intercept:finite,
  preprocessing:z.object({kind:z.literal("StandardScaler"),mean:z.array(finite),scale:z.array(finite.positive()),absorbed_into_raw_coefficients:z.literal(true)}),
  fit_seasons:z.tuple([z.number().int().min(2011),z.number().int().max(2021)]),fit_n:count.min(1),
  calibration:z.object({method:z.literal("Platt"),coefficient:finite,intercept:finite,season:z.number().int().min(2017).max(2022),n:count.min(1)})});
// Domain inventory is validated separately from research probabilities: unavailable domains cannot become model inputs.
export const domainSchema = z.object({id:z.string(),name:z.string(),incumbent_used:z.boolean(),challenger_used:z.boolean(),status:z.string(),
  source:z.object({name:z.string(),url:sourceURL,license:z.string(),historical_availability:z.string()}),
  prediction_time_rule:z.string(),transformation:z.string(),missing_behavior:z.string(),leakage_test:z.string(),
  contribution:z.object({method:z.string(),full_minus_ablated_brier:finite,uncertainty,n:count.min(1),not_causal:z.literal(true)}).nullable(),
});
export const researchSchema = z.object({
  schema_version:z.literal(1),mode:z.literal("challenger-research"),status:z.literal("research-only-not-promoted"),generated_at:timestamp,
  model:model.extend({id:z.string()}),incumbent_model_id:z.literal(frozen.model.id),
  provenance:z.object({source_sha256:z.literal("20f573837dac7d9ea41dade07b165de6164b3370d60e49d5242e5255cabb7d01"),protocol_sha256:digest,frozen_manifest_sha256:z.literal("2896a526ed8035b1674a6beb3c8d27c76ba4b3f466309bfeb729c6ddbf80f957"),code_sha256:z.record(z.string(),digest),python:z.string(),packages:z.record(z.string(),z.string())}),
  evaluation:z.object({diagnostic_season:z.literal(2023),diagnostic_status:z.literal("selection-exposed-retrospective"),challenger:metric,incumbent:metric,home:metric,coin:metric,raw_challenger:metric,incumbent_recipe:metric,
    backtests:z.array(z.object({season:z.number().int().min(2018).max(2023),fit_seasons:z.tuple([z.number().int(),z.number().int()]),fit_n:count.min(1),calibration_season:z.number().int(),calibration_n:count.min(1),metrics:z.record(z.string(),metric),challenger_ece:probability,calibration})).length(6),
    pooled:z.record(z.string(),metric),calibration,pooled_calibration:calibration,pooled_ece:probability,
    domain_ablations:z.array(z.object({domain:z.string(),removed:z.array(z.string()),ablated:metric,full_minus_ablated_brier:finite,uncertainty})),
    uncertainty:z.object({pooled_vs_recipe:uncertainty,diagnostic_vs_frozen_incumbent:uncertainty}),
  }),
  fold_models:z.array(z.object({season:z.number().int().min(2018).max(2023),model})).length(6),
  predictions:z.array(z.object({id:z.string(),season:z.number().int().min(2018).max(2023),week:count.min(1).max(18),gameday:z.string(),home_win:z.union([z.literal(0),z.literal(1)]),features:z.record(z.string(),finite),probabilities:z.record(z.string(),probability)})).max(2000),
  domains:z.array(domainSchema).length(12),limitations:z.array(z.string()),
  promotion:z.object({eligible:z.literal(false),approval_required:z.literal(true),criteria:z.record(z.string(),z.boolean()),blockers:z.array(z.string()).min(1)}),
  attribution:z.object({name:z.string(),url:sourceURL,license:z.string(),license_url:sourceURL}),
}).superRefine((data,ctx)=>{
  const fail=(message:string)=>ctx.addIssue({code:"custom",message});
  const close=(a:number,b:number)=>Math.abs(a-b)<1e-9;
  const mean=(values:number[])=>values.reduce((a,b)=>a+b,0)/values.length;
  const folds=new Map(data.fold_models.map(f=>[f.season,f.model]));
  if(folds.size!==6 || new Set(data.evaluation.backtests.map(f=>f.season)).size!==6 || new Set(data.predictions.map(p=>p.id)).size!==data.predictions.length || new Set(data.domains.map(d=>d.id)).size!==12) fail("Duplicate research evidence");
  for(const f of data.fold_models){
    if(f.model.fit_seasons[1]>=f.model.calibration.season || f.model.calibration.season!==f.season-1 || f.model.features.length!==f.model.coefficients.length || f.model.features.length!==f.model.preprocessing.mean.length || f.model.features.length!==f.model.preprocessing.scale.length) fail("Invalid chronological model split or preprocessing");
  }
  for(const p of data.predictions){
    const m=folds.get(p.season);
    if(!m || !p.id.startsWith(`${p.season}_`) || !p.gameday.startsWith(String(p.season)) && !p.gameday.startsWith(String(p.season+1))) {fail("Prediction/model season mismatch");continue;}
    let logit=m.intercept;
    for(const [i,name] of m.features.entries()) {
      if(p.features[name]===undefined) fail("Research input missing");
      logit+=p.features[name]*m.coefficients[i];
    }
    if(!close(p.probabilities.raw_challenger,1/(1+Math.exp(-logit))) || !close(p.probabilities.challenger,1/(1+Math.exp(-(m.calibration.intercept+m.calibration.coefficient*logit))))) fail("Challenger probability arithmetic mismatch");
    if(p.probabilities.coin!==.5) fail("Invalid coin baseline");
    if(p.season===2023){const z=frozen.model.intercept+frozen.model.features.reduce((sum,name,i)=>sum+p.features[name]*frozen.model.coefficients[i],0);if(!close(p.probabilities.frozen_incumbent,1/(1+Math.exp(-z))))fail("Frozen comparator arithmetic mismatch");}
  }
  type Row=typeof data.predictions[number];
  function check(m:z.infer<typeof metric>,rows:Row[],key:string){
    if(m.n!==rows.length || rows.some(r=>r.probabilities[key]===undefined)) {fail("Metric population mismatch");return;}
    if(!close(m.accuracy,mean(rows.map(r=>Number((r.probabilities[key]>=.5?1:0)===r.home_win)))) || !close(m.brier,mean(rows.map(r=>(r.probabilities[key]-r.home_win)**2))) || !close(m.log_loss,mean(rows.map(r=>-Math.log(Math.max(Number.EPSILON,r.home_win?r.probabilities[key]:1-r.probabilities[key])))))) fail("Research metric arithmetic mismatch");
  }
  function checkCalibration(bins:z.infer<typeof calibration>,rows:Row[]){
    if(new Set(bins.map(b=>b.bin)).size!==bins.length || bins.reduce((n,b)=>n+b.count,0)!==rows.length)fail("Calibration population mismatch");
    for(const b of bins){const items=rows.filter(r=>Math.min(9,Math.floor(r.probabilities.challenger*10))===b.bin);if(b.count!==items.length || !close(b.predicted,mean(items.map(r=>r.probabilities.challenger))) || !close(b.observed,mean(items.map(r=>r.home_win))))fail("Research calibration mismatch");}
  }
  for(const f of data.evaluation.backtests){const rows=data.predictions.filter(r=>r.season===f.season);if(f.fit_seasons[1]>=f.calibration_season || f.calibration_season>=f.season)fail("Leaking research split");for(const [key,m]of Object.entries(f.metrics))check(m,rows,key);checkCalibration(f.calibration,rows);}
  for(const [key,m]of Object.entries(data.evaluation.pooled))check(m,data.predictions,key);
  const diagnostic=data.predictions.filter(r=>r.season===2023);
  for(const key of ["challenger","home","coin","raw_challenger","incumbent_recipe"] as const)check(data.evaluation[key],diagnostic,key);
  check(data.evaluation.incumbent,diagnostic,"frozen_incumbent");
  checkCalibration(data.evaluation.calibration,diagnostic);checkCalibration(data.evaluation.pooled_calibration,data.predictions);
  for(const u of Object.values(data.evaluation.uncertainty))if(u.low>u.high || u.mean<u.low || u.mean>u.high)fail("Invalid uncertainty interval");
  if(!close(data.evaluation.uncertainty.pooled_vs_recipe.mean,data.evaluation.pooled.challenger.brier-data.evaluation.pooled.incumbent_recipe.brier) || !close(data.evaluation.uncertainty.diagnostic_vs_frozen_incumbent.mean,data.evaluation.challenger.brier-data.evaluation.incumbent.brier))fail("Paired uncertainty mean mismatch");
  const requiredDomains=["prior_strength","current_performance","efficiency","opponent_adjusted","recent_trends","home_road","scoring_margins","rest_travel","quarterback","injuries","weather","developments"];
  const incumbentDomains=new Set(["current_performance","recent_trends","scoring_margins","rest_travel"]);
  const challengerDomains=new Set(["prior_strength","current_performance","opponent_adjusted","recent_trends","home_road","scoring_margins","rest_travel"]);
  for(const d of data.domains) {
    if(!requiredDomains.includes(d.id) || d.incumbent_used!==incumbentDomains.has(d.id) || d.challenger_used!==challengerDomains.has(d.id) || Boolean(d.contribution)!==d.challenger_used) fail("Domain usage does not match trained feature definitions");
    const ablation=data.evaluation.domain_ablations.find(a=>a.domain===d.id);
    if(d.contribution && (!ablation || !close(d.contribution.full_minus_ablated_brier,ablation.full_minus_ablated_brier) || d.contribution.n!==data.predictions.length)) fail("Domain contribution lacks measured ablation evidence");
  }
  const ece=(bins:z.infer<typeof calibration>)=>bins.reduce((sum,b)=>sum+b.count*Math.abs(b.predicted-b.observed),0)/bins.reduce((sum,b)=>sum+b.count,0);
  if(!close(data.evaluation.pooled_ece,ece(data.evaluation.pooled_calibration)))fail("Pooled calibration error mismatch");
  for(const f of data.evaluation.backtests)if(!close(f.challenger_ece,ece(f.calibration)))fail("Fold calibration error mismatch");
  if(JSON.stringify(data.model)!==JSON.stringify(folds.get(2023)))fail("Final research model differs from its evaluated fold");
});
export type Research=z.infer<typeof researchSchema>;
export type Domain=z.infer<typeof domainSchema>;
export const loadResearch=()=>loadVersioned("research","challenger",researchSchema);
