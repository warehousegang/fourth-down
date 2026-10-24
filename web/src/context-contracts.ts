import { z } from "zod";
import { compareTimestamp, count, digest, finite, loadVersioned, probability, sourceURL, timestamp } from "./versioned-artifact";
const sourceId=z.enum(["injuries","depth_charts","stats_team"]);
const observation=z.object({status:z.enum(["observed","unavailable"]),source_id:sourceId,observed_at:timestamp,report_published_at:timestamp.nullable(),warnings:z.array(z.string())});
const ratios=z.object({completion_rate:probability.nullable(),passing_yards_per_attempt:finite.nullable(),rushing_yards_per_attempt:finite.nullable()});
const totals=z.object({attempts:count,completions:count,carries:count,passing_yards:finite.int(),rushing_yards:finite.int()});
const team=z.object({team:z.string(),
  injuries:observation.extend({source_id:z.literal("injuries"),report_published_at:z.null(),players:z.array(z.object({name:z.string().min(1),player_id:z.string().nullable(),position:z.string(),report_status:z.string(),practice_status:z.string(),report_issue:z.string().nullable(),practice_issue:z.string().nullable()})).max(100)}),
  quarterback:observation.extend({source_id:z.literal("depth_charts"),report_published_at:z.null(),source_recorded_at:timestamp.nullable(),confirmed_starter:z.null(),depth_chart:z.array(z.object({name:z.string().min(1),player_id:z.string().min(1),rank:count.min(1)})).max(20)}),
  performance:observation.extend({source_id:z.literal("stats_team"),report_published_at:z.null(),metrics:z.object({offense:ratios,opponent_allowed:ratios}).nullable(),totals:z.object({offense:totals,opponent_allowed:totals}).nullable(),completed_game_ids:z.array(z.string()).max(17)}),
});
export const contextSchema=z.object({
  schema_version:z.literal(1),mode:z.literal("current-context"),season:z.number().int().min(2026),week:count.min(1).max(18).nullable(),
  generated_at:timestamp,as_of:timestamp,valid_until:timestamp,affects_probability:z.literal(false),pipeline_sha256:digest,receipt_sha256:digest,
  schedule_source:z.object({source_url:sourceURL,raw_sha256:digest,source_updated_at:timestamp,retrieved_at:timestamp}),
  sources:z.array(z.object({id:sourceId,url:sourceURL,sha256:digest,source_updated_at:timestamp,retrieved_at:timestamp,license:z.string(),license_url:sourceURL,asset_id:count,file:z.string()})).length(3),
  games:z.array(z.object({id:z.string(),home:z.string(),away:z.string(),week:count.min(1).max(18),kickoff:timestamp,cutoff:timestamp,teams:z.object({home:team,away:team})})).max(32),limitations:z.array(z.string()),
}).superRefine((d,ctx)=>{
  const fail=(message:string)=>ctx.addIssue({code:"custom",message});
  const close=(a:number|null,b:number|null)=>a===null||b===null?a===b:Math.abs(a-b)<1e-12;
  if(compareTimestamp(d.as_of,d.generated_at)>0 || compareTimestamp(d.schedule_source.source_updated_at,d.schedule_source.retrieved_at)>0 || compareTimestamp(d.schedule_source.retrieved_at,d.as_of)>=0)fail("Invalid context ordering");
  if(d.schedule_source.source_url!==`https://github.com/sportsdataverse/sportsdataverse-data/releases/download/nfl_ngs_schedules/ngs_schedule_${d.season}.csv`)fail("Context schedule is not season-isolated");
  if(new Set(d.sources.map(s=>s.id)).size!==3 || new Set(d.games.map(g=>g.id)).size!==d.games.length)fail("Duplicate context sources/games");
  const files={injuries:`injuries_${d.season}.csv`,depth_charts:`depth_charts_${d.season}.parquet`,stats_team:`stats_team_week_${d.season}.csv`};
  const sources=new Map(d.sources.map(s=>[s.id,s]));
  for(const source of d.sources){
    if(source.url!==`https://github.com/nflverse/nflverse-data/releases/download/${source.id}/${files[source.id]}` || source.file!==`${source.sha256}-${files[source.id]}`)fail("Context source is not the permitted per-season asset");
    if(compareTimestamp(source.source_updated_at,source.retrieved_at)>0 || compareTimestamp(source.retrieved_at,d.as_of)>=0)fail("Context source was not observed before cutoff");
  }
  if(Date.parse(d.valid_until)>Math.min(Date.parse(d.generated_at)+24*3600000,...d.sources.map(s=>Date.parse(s.source_updated_at)+48*3600000)))fail("Context freshness exceeds policy");
  for(const g of d.games){
    if(!g.id.startsWith(`ngs-${d.season}-`) || g.home===g.away || g.cutoff!==d.as_of || compareTimestamp(d.generated_at,g.kickoff)>=0)fail("Context is not pregame");
    for(const side of ["home","away"] as const){
      const t=g.teams[side];if(t.team!==g[side])fail("Context team mismatch");
      for(const value of [t.injuries,t.quarterback,t.performance]){
        const source=sources.get(value.source_id);
        if(!source || value.observed_at!==source.retrieved_at || compareTimestamp(value.observed_at,g.cutoff)>=0 || value.report_published_at && (compareTimestamp(value.report_published_at,value.observed_at)>0 || compareTimestamp(value.report_published_at,g.cutoff)>=0))fail("Context evidence timestamp mismatch");
        if(value.status==="observed" && source && Date.parse(g.cutoff)-Date.parse(source.source_updated_at)>48*3600000)fail("Stale source marked observed");
      }
      if(t.injuries.status==="observed" ? !t.injuries.players.length : t.injuries.players.length)fail("Injury status/payload mismatch");
      if(new Set(t.injuries.players.map(p=>p.player_id??p.name)).size!==t.injuries.players.length)fail("Duplicate injury report");
      if(t.quarterback.status==="observed" ? !t.quarterback.depth_chart.length || !t.quarterback.source_recorded_at : t.quarterback.depth_chart.length)fail("Quarterback status/payload mismatch");
      if(new Set(t.quarterback.depth_chart.map(p=>p.player_id)).size!==t.quarterback.depth_chart.length)fail("Duplicate quarterback identity");
      if(t.quarterback.status==="observed" && t.quarterback.source_recorded_at && (Date.parse(g.cutoff)-Date.parse(t.quarterback.source_recorded_at)>48*3600000 || compareTimestamp(t.quarterback.source_recorded_at,t.quarterback.observed_at)>0 || compareTimestamp(t.quarterback.source_recorded_at,sources.get("depth_charts")!.source_updated_at)>0 || compareTimestamp(t.quarterback.source_recorded_at,g.cutoff)>=0))fail("Stale quarterback report");
      const p=t.performance;
      if(p.status==="unavailable") {if(p.metrics || p.totals || p.completed_game_ids.length)fail("Unavailable performance contains metrics");continue;}
      if(!p.metrics || !p.totals || !p.completed_game_ids.length) {fail("Observed performance lacks inputs");continue;}
      if(new Set(p.completed_game_ids).size!==p.completed_game_ids.length || p.completed_game_ids.some(id=>!id.startsWith(`ngs-${d.season}-`) || id===g.id))fail("Invalid performance game population");
      for(const role of ["offense","opponent_allowed"] as const){const total=p.totals[role],metric=p.metrics[role];if(total.completions>total.attempts || !close(metric.completion_rate,total.attempts?total.completions/total.attempts:null) || !close(metric.passing_yards_per_attempt,total.attempts?total.passing_yards/total.attempts:null) || !close(metric.rushing_yards_per_attempt,total.carries?total.rushing_yards/total.carries:null))fail("Performance ratio arithmetic mismatch");}
    }
  }
});
export type Context=z.infer<typeof contextSchema>;
export const loadContext=()=>loadVersioned("context","context",contextSchema);
