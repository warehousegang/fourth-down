import type { ForecastRecord, Operations } from "./operations-contracts";

export const MAX_DEMO_DRAWS = 100_000;

/** Mulberry32 v1, unsigned 32-bit seed. One uniform draw per Bernoulli trial. */
export function simulateBernoulli(probability: number, count: number, seed: number) {
  if (typeof probability !== "number" || !Number.isFinite(probability) || probability < 0 || probability > 1) throw new Error("Probability must be a finite number from 0 to 1.");
  if (!Number.isInteger(count) || count < 1 || count > MAX_DEMO_DRAWS) throw new Error("Choose a whole-number draw count from 1 to 100,000.");
  if (!Number.isInteger(seed) || seed < 0 || seed > 0xffffffff) throw new Error("Choose a whole-number seed from 0 to 4,294,967,295.");
  let state = seed >>> 0;
  let wins = 0;
  for (let i = 0; i < count; i++) {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t ^= t + Math.imul(t ^ (t >>> 7), 61 | t);
    const uniform = ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    if (uniform < probability) wins++;
  }
  return { algorithm: "Mulberry32 v1 + Bernoulli(p)", probability, count, seed, wins, losses: count - wins,
    frequency: wins / count, standardError: Math.sqrt(probability * (1 - probability) / count) };
}

/** Only verified latest pregame receipts matching the saved upcoming schedule. */
export function demonstrationForecasts(data: Operations, now: number): ForecastRecord[] {
  if (!Number.isFinite(now) || now < Date.parse(data.generated_at)) return [];
  return data.games.flatMap(game => {
    const forecast = data.catalog.find(f => f.id === game.latest_forecast_id);
    const schedule = data.schedule.find(g => g.id === game.id);
    if (!forecast || !schedule || game.status !== "scheduled" || schedule.status !== "scheduled" || game.result
      || !forecast.latest || !forecast.eligible || forecast.exclusions.length || forecast.forecast_status !== "available"
      || forecast.home_probability === null || forecast.away_probability === null || !forecast.kickoff
      || forecast.game_id !== game.id || forecast.home !== schedule.home || forecast.away !== schedule.away
      || forecast.kickoff !== game.kickoff || forecast.kickoff !== schedule.kickoff || Date.parse(forecast.kickoff) <= now) return [];
    return [forecast];
  });
}

/** A fixed, inspectable research template. It performs no inference, experiment or data fetch. */
export function researchWalkthrough(forecast: ForecastRecord) {
  const strongest = [...forecast.factors].sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution) || a.key.localeCompare(b.key))[0];
  return {
    plan: `Inspect the saved ${forecast.away} at ${forecast.home} forecast and identify one testable research question. Keep the original probability and cutoff unchanged.`,
    hypothesis: strongest
      ? `Test whether ${strongest.label.toLowerCase()}, the largest absolute saved feature contribution in this matchup, improves Brier score across authorized retrospective season-week blocks. This is a proposed comparison, not an established effect or explanation of a game result.`
      : "No verified feature contribution is available; do not infer a research finding.",
    evidenceNeeded: "A declared ablation protocol, same-game comparisons on approved historical partitions, and season-week uncertainty intervals. No new experiment has been run by this walkthrough.",
    proposal: "Human review proposal: assess the cited inputs, decide whether to authorize the stated comparison, and record the decision before any experiment. No probability, coefficient, forecast, or model promotion changes are made. The 2024–2025 holdout remains locked.",
  };
}
