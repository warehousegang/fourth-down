import type { CurrentArtifact, CurrentGame } from "./current-contracts";
import type { ForecastRecord, Operations } from "./operations-contracts";
import { compareTimestamp } from "./versioned-artifact";

export const SOURCE_STALE_REASON = "Source is over 48 hours old; refresh before using forecasts";
export type DisplayGame = CurrentGame | Operations["schedule"][number];
export type DisplayDecision = {state: "fresh" | "older" | "archived" | "unavailable"; forecast_id: string | null; reason: string | null};

/** Inputs must have passed their checksummed schemas. Mirrors ml/freshness.py. */
export function selectDisplayForecast(current: CurrentArtifact, game: DisplayGame, operations: Operations | null, now: number): DisplayDecision {
  const blocked = (reason: string): DisplayDecision => ({state:"unavailable",forecast_id:null,reason});
  if (!operations) return blocked("Verified forecast history is unavailable.");
  if (Date.parse(current.generated_at)>now || Date.parse(operations.generated_at)>now) return blocked("Forecast evidence is dated in the future.");
  if (operations.season!==current.season || compareTimestamp(operations.source.retrieved_at,current.source.retrieved_at)<0) return blocked("Forecast and latest source evidence do not match.");
  const scheduled=operations.schedule.find(g=>g.id===game.id);
  const identity=["home","away","kickoff","day","week","season"] as const;
  if (!scheduled || identity.some(k=>scheduled[k]!==game[k])) return blocked("The observed schedule changed; inspect the retained forecast history.");
  const halted=["postponed","canceled"].includes(scheduled.status);
  if (!game.kickoff&&!halted) return blocked("Kickoff is unconfirmed; no eligible pregame prediction is displayed.");
  const archived=halted||now>=Date.parse(game.kickoff!);
  const historicExclusions=new Set(["Game is canceled or awaiting confirmed rescheduled kickoff","Schedule identity changed; a new pregame forecast is required"]);
  if (!archived) {
    if (scheduled.status!=="scheduled" || !["", "SCHEDULED", "PREGAME", "PRE_GAME"].includes(game.source_phase)) return blocked("The matchup is not confirmed scheduled.");
    if (!("schedule_fingerprint" in game)) return blocked("No current pregame decision is available; inspect Forecast History.");
    if (game.status!=="available" && game.reason!==SOURCE_STALE_REASON) return blocked(game.reason || "Required forecast inputs are unavailable.");
    if (operations.source.raw_sha256!==current.source.raw_sha256) return blocked("Forecast and latest source evidence do not match.");
  }
  const candidates=operations.catalog.filter(f=>f.game_id===game.id && (f.eligible&&!f.exclusions.length||halted&&f.exclusions.length>0&&f.exclusions.every(e=>historicExclusions.has(e))) && f.forecast_status==="available"
    && identity.filter(k=>!halted||!["kickoff","day"].includes(k)).every(k=>f[k]===game[k])
    && (archived || "schedule_fingerprint" in game && f.schedule_fingerprint===game.schedule_fingerprint && f.source.raw_sha256===current.source.raw_sha256)
    && Date.parse(f.generated_at)<=now && f.kickoff!==null && compareTimestamp(f.generated_at,f.kickoff)<0);
  candidates.sort((a,b)=>compareTimestamp(a.generated_at,b.generated_at) || a.id.localeCompare(b.id));
  // A recorded evaluation designation is authoritative. Never pick another receipt for its outcome.
  const finalId=operations.games.find(g=>g.id===game.id)?.final_forecast_id;
  const record=archived && finalId ? candidates.find(f=>f.id===finalId) : candidates.at(-1);
  if (!record) return blocked("No eligible forecast with verified unchanged inputs is available.");
  if (archived) return {state:"archived",forecast_id:record.id,reason:null};
  const older=now>=Date.parse(record.valid_until) || record.generated_at!==current.generated_at;
  return {state:older?"older":"fresh",forecast_id:record.id,reason:null};
}

/** Keep this week, the most recent started week and unresolved archived games after refresh. */
export function displayGames(current: CurrentArtifact, operations: Operations | null, now: number, selectedId?: string | null): DisplayGame[] {
  if (!operations || operations.season!==current.season || Date.parse(operations.generated_at)>now) return current.games;
  const ids=new Set(operations.games.map(g=>g.id));
  const recorded=operations.schedule.filter(g=>ids.has(g.id));
  const recentWeek=Math.max(0,...recorded.filter(g=>g.kickoff && Date.parse(g.kickoff)<=now).map(g=>g.week));
  const games=new Map<string,DisplayGame>(current.games.map(g=>[g.id,g]));
  for (const g of recorded) if (!games.has(g.id) && (g.id===selectedId || g.week===current.week || g.week===recentWeek || ["in_progress","unknown","postponed"].includes(g.status))) games.set(g.id,g);
  return [...games.values()].sort((a,b)=>(a.kickoff??"9999").localeCompare(b.kickoff??"9999") || a.id.localeCompare(b.id));
}

export function displayRecord(operations: Operations | null, choice: DisplayDecision): ForecastRecord | null {
  return operations?.catalog.find(f=>f.id===choice.forecast_id) ?? null;
}
