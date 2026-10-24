import { afterEach, expect, it, vi } from "vitest";
import { webcrypto } from "node:crypto";
import { operationsSchema, loadOperations, type Operations } from "./operations-contracts";
import { researchSchema, type Research } from "./research-contracts";
import { completedFixture, operationsCapture, operationsFixture, researchFixture } from "./intelligence-fixtures";

afterEach(()=>vi.unstubAllGlobals());
it("validates captured archive and keeps absent outcomes unestablished",()=>{
  const data=operationsFixture();
  expect(data.catalog.length).toBeGreaterThanOrEqual(data.games.length);
  expect(data.games.every(g=>g.result===null&&g.final_forecast_id===null)).toBe(true);
  expect(data.metrics.primary.accuracy).toBeNull();
  expect(data.metrics.primary.count).toBe(0);
});
it("independently checks every captured research probability and score",()=>{
  const data=researchFixture();expect(data.predictions).toHaveLength(1576);expect(data.domains).toHaveLength(12);expect(data.promotion.eligible).toBe(false);
});
it("validates completed primary and repeated-snapshot evaluation arithmetic",()=>{
  const data=completedFixture();expect(data.metrics.primary.count).toBe(1);expect(data.metrics.all_snapshots.count).toBe(data.catalog.length);
});
const operationsTampering:[string,(d:Operations)=>void][]=[
  ["probability",d=>{d.catalog[0].home_probability=.99;}],
  ["feature",d=>{d.catalog[0].features.margin_diff+=1;}],
  ["future observation",d=>{d.catalog[0].history.home[0].observed_at=d.catalog[0].generated_at;}],
  ["future final designation",d=>{d.games[0].final_forecast_id=d.games[0].latest_forecast_id;d.catalog.find(f=>f.id===d.games[0].latest_forecast_id)!.selected_final=true;}],
  ["invented metric",d=>{d.metrics.primary.accuracy=.9;}],
  ["protected season",d=>{d.season=2025;}],
  ["traversal",d=>{d.catalog[0].artifact_file="../demo.json";}],
];
it.each(operationsTampering)("rejects archive %s",(_,change)=>{const data=operationsFixture();change(data);expect(operationsSchema.safeParse(data).success).toBe(false);});
it.each(["brier","log_loss","surprise","outcome_home"] as const)("rejects tampered completed %s",field=>{const d=completedFixture();if(field==="outcome_home")d.games[0].evaluations[0].outcome_home=0;else d.games[0].evaluations[0][field]=999;expect(operationsSchema.safeParse(d).success).toBe(false);});
it("rejects altered calibration and aggregate baselines",()=>{const d=completedFixture();d.metrics.primary.baselines.home_rate.brier=.99;d.metrics.primary.calibration.find(b=>b.count)!.home_win_rate=0;expect(operationsSchema.safeParse(d).success).toBe(false);});
const researchTampering:[string,(d:Research)=>void][]=[
  ["model coefficient",d=>{d.fold_models[0].model.coefficients[0]+=1;}],
  ["calibration",d=>{d.evaluation.pooled_calibration[0].observed=.99;}],
  ["validation metric",d=>{d.evaluation.challenger.brier=.01;}],
  ["future fitting",d=>{d.fold_models[0].model.fit_seasons[1]=2021;}],
  ["protected season",d=>{d.predictions[0].season=2025;}],
  ["promotion",d=>{(d.promotion as {eligible:boolean}).eligible=true;}],
];
it.each(researchTampering)("rejects research %s",(_,change)=>{const d=researchFixture();change(d);expect(researchSchema.safeParse(d).success).toBe(false);});
it("loads only checksum-matched operations and rejects corrupt bytes",async()=>{
  vi.stubGlobal("crypto",webcrypto);const fetch=vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(operationsCapture.pointer))).mockResolvedValueOnce(new Response(operationsCapture.text));vi.stubGlobal("fetch",fetch);
  expect((await loadOperations()).data.mode).toBe("forecast-operations");
  fetch.mockResolvedValueOnce(new Response(JSON.stringify(operationsCapture.pointer))).mockResolvedValueOnce(new Response(operationsCapture.text+" "));
  await expect(loadOperations()).rejects.toThrow(/integrity/);
});
it("rejects pointer traversal before requesting an artifact",async()=>{
  const fetch=vi.fn().mockResolvedValue(new Response(JSON.stringify({...operationsCapture.pointer,file:"../demo.json"})));vi.stubGlobal("fetch",fetch);await expect(loadOperations()).rejects.toThrow(/integrity/);expect(fetch).toHaveBeenCalledTimes(1);
});
it("retains removed stable IDs as excluded, unscored unknown games",()=>{
  const d=operationsFixture();const game=d.games[0];d.schedule=d.schedule.filter(g=>g.id!==game.id);game.status="unknown";
  for(const f of d.catalog.filter(f=>f.game_id===game.id)){f.eligible=false;f.exclusions=["Stable game ID missing from current schedule"];}
  expect(operationsSchema.safeParse(d).success).toBe(true);
});
it("rejects claiming unavailable quarterback inputs affect the operational model",()=>{
  const d=researchFixture();d.domains.find(x=>x.id==="quarterback")!.incumbent_used=true;expect(researchSchema.safeParse(d).success).toBe(false);
});
it("rejects an invented domain identifier or unmeasured contribution",()=>{
  const d=researchFixture();d.domains[0].id="invented-domain";expect(researchSchema.safeParse(d).success).toBe(false);
  const valid=researchFixture();valid.domains.find(x=>x.challenger_used)!.contribution=null;expect(researchSchema.safeParse(valid).success).toBe(false);
});
it("independently rejects falsified expected calibration error",()=>{
  const d=researchFixture();d.evaluation.pooled_ece=.001;expect(researchSchema.safeParse(d).success).toBe(false);
});
it("rejects a replaced fixed home-rate baseline even when its scores are internally consistent",()=>{
  const d=completedFixture();const b=d.games[0].evaluations[0].baseline.home_rate;b.probability=.8;b.correct=true;b.brier=.04;b.log_loss=-Math.log(.8);expect(operationsSchema.safeParse(d).success).toBe(false);
});
it("rejects future analysis evidence and malformed empty calibration ranges",()=>{
  const d=completedFixture();d.games[0].analysis!.facts[0].observed_at="2027-01-01T00:00:00Z";expect(operationsSchema.safeParse(d).success).toBe(false);
  const empty=operationsFixture();empty.metrics.primary.calibration[0].upper=.9;expect(operationsSchema.safeParse(empty).success).toBe(false);
});
it("keeps tied outcomes out of binary metrics and verifies both exclusion populations",()=>{
  const d=completedFixture();d.games[0].result!.away_score=d.games[0].result!.home_score;d.games[0].result!.tie=true;d.games[0].evaluations=[];
  const empty={count:0,accuracy:null,brier:null,log_loss:null};
  for(const key of ["primary","all_snapshots"] as const){const m=d.metrics[key];Object.assign(m,empty,{game_count:0,ties_excluded:key==="primary"?1:d.catalog.filter(f=>f.eligible).length});m.baselines={coin_flip:{...empty},home_rate:{...empty}};m.by_season=[];m.calibration=m.calibration.map(b=>({...b,count:0,mean_probability:null,home_win_rate:null,brier:null}));}
  expect(operationsSchema.safeParse(d).success).toBe(true);d.metrics.all_snapshots.ties_excluded=99;expect(operationsSchema.safeParse(d).success).toBe(false);
});
