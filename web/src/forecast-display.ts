import type { CurrentArtifact, CurrentGame } from "./current-contracts";
import type { ForecastRecord, Operations } from "./operations-contracts";
import { compareTimestamp } from "./versioned-artifact";

export const SOURCE_STALE_REASON = "Source is over 48 hours old; refresh before using forecasts";
export type DisplayDecision = {state: "fresh" | "older" | "unavailable"; forecast_id: string | null; reason: string | null};

/** Inputs must have passed their checksummed schemas. Mirrors ml/freshness.py. */
export function selectDisplayForecast(current: CurrentArtifact, game: CurrentGame, operations: Operations | null, now: number): DisplayDecision {
  const blocked = (reason: string): DisplayDecision => ({state:"unavailable",forecast_id:null,reason});
  if (!operations) return blocked("Verified forecast history is unavailable.");
  if (Date.parse(current.generated_at)>now || Date.parse(operations.generated_at)>now) return blocked("Forecast evidence is dated in the future.");
  if (!game.kickoff || now>=Date.parse(game.kickoff)) return blocked("Kickoff is unconfirmed or has passed; no upcoming probability is displayed.");
  if (!["", "SCHEDULED", "PREGAME", "PRE_GAME"].includes(game.source_phase)) return blocked("The matchup is not confirmed scheduled.");
  if (game.status!=="available" && game.reason!==SOURCE_STALE_REASON) return blocked(game.reason || "Required forecast inputs are unavailable.");
  if (operations.season!==current.season || compareTimestamp(operations.source.retrieved_at,current.source.retrieved_at)<0 || operations.source.raw_sha256!==current.source.raw_sha256) return blocked("Forecast and latest source evidence do not match.");
  const scheduled=operations.schedule.find(g=>g.id===game.id);
  const identity=["home","away","kickoff","day","week"] as const;
  if (!scheduled || scheduled.status!=="scheduled" || identity.some(k=>scheduled[k]!==game[k])) return blocked("The observed schedule changed or the game is no longer scheduled.");
  const candidates=operations.catalog.filter(f=>f.game_id===game.id && f.eligible && !f.exclusions.length && f.forecast_status==="available"
    && f.schedule_fingerprint===game.schedule_fingerprint && identity.every(k=>f[k]===game[k])
    && f.source.raw_sha256===current.source.raw_sha256 && Date.parse(f.generated_at)<=now && compareTimestamp(f.generated_at,game.kickoff!)<0);
  candidates.sort((a,b)=>compareTimestamp(a.generated_at,b.generated_at) || a.id.localeCompare(b.id));
  const record=candidates.at(-1);
  if (!record) return blocked("No eligible forecast with verified unchanged inputs is available.");
  const older=now>=Date.parse(record.valid_until) || record.generated_at!==current.generated_at;
  return {state:older?"older":"fresh",forecast_id:record.id,reason:null};
}

export function displayRecord(operations: Operations | null, choice: DisplayDecision): ForecastRecord | null {
  return operations?.catalog.find(f=>f.id===choice.forecast_id) ?? null;
}
