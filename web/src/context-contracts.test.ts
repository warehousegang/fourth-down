import { expect, it } from "vitest";
import { contextSchema, type Context } from "./context-contracts";
import { contextFixture } from "./intelligence-fixtures";
it("validates genuine season-isolated annotations and independently derives descriptive ratios",()=>{
  const d=contextFixture();expect(d.games.length).toBeGreaterThan(0);expect(d.affects_probability).toBe(false);expect(d.games[0].teams.home.injuries.report_published_at).toBeNull();expect(d.games[0].teams.home.quarterback.confirmed_starter).toBeNull();
});
const changes:[string,(d:Context)=>void][]=[
  ["claimed probability influence",d=>{(d as {affects_probability:boolean}).affects_probability=true;}],
  ["falsified completion ratio",d=>{d.games[0].teams.home.performance.metrics!.offense.completion_rate=.99;}],
  ["same-game results",d=>{d.games[0].teams.home.performance.completed_game_ids[0]=d.games[0].id;}],
  ["protected source season",d=>{d.sources[0].url=d.sources[0].url.replace("2026","2025");}],
  ["injury publication timestamp invented",d=>{(d.games[0].teams.home.injuries as {report_published_at:string|null}).report_published_at=d.as_of;}],
  ["starter falsely confirmed",d=>{(d.games[0].teams.home.quarterback as {confirmed_starter:string|null}).confirmed_starter="Claimed starter";}],
  ["observed after cutoff",d=>{d.games[0].teams.home.injuries.observed_at=d.as_of;}],
  ["generated at kickoff",d=>{d.generated_at=d.games[0].kickoff;}],
  ["unavailable carrying observations",d=>{d.games[0].teams.home.performance.status="unavailable";}],
];
it.each(changes)("rejects %s",(_,change)=>{const d=contextFixture();change(d);expect(contextSchema.safeParse(d).success).toBe(false);});
it("accepts explicit unavailable reports without inferring healthy players",()=>{
  const d=contextFixture();const side=d.games[0].teams.home;side.injuries.status="unavailable";side.injuries.players=[];side.injuries.warnings=["Current-week report not found; no availability inferred"];
  side.quarterback.status="unavailable";side.quarterback.depth_chart=[];side.quarterback.report_published_at=null;side.quarterback.source_recorded_at=null;
  side.performance.status="unavailable";side.performance.metrics=null;side.performance.totals=null;side.performance.completed_game_ids=[];
  expect(contextSchema.safeParse(d).success).toBe(true);
});
it("rejects a provider depth snapshot dated after publication of its source asset",()=>{
  const d=contextFixture();d.games[0].teams.home.quarterback.source_recorded_at="2026-10-24T13:58:00Z";expect(contextSchema.safeParse(d).success).toBe(false);
});
