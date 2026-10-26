import type { ForecastRecord, Operations } from "./operations-contracts";

/** Exact distribution of the number of successes in independent Bernoulli trials.
 * Descending convolution uses O(n²) time / O(n) space; no sampling or random seed.
 */
export function poissonBinomial(probabilities: readonly number[]): number[] {
  const mass = [1];
  for (const p of probabilities) {
    if (!Number.isFinite(p) || p < 0 || p > 1) throw new RangeError("Invalid probability");
    mass.push(0);
    for (let k = mass.length - 1; k >= 0; k--) {
      mass[k] = mass[k] * (1 - p) + (k ? mass[k - 1] * p : 0);
    }
  }
  return mass;
}

// Match the existing lifecycle's logarithm floor; never change the saved probability.
const surprise = (p: number) => -Math.log(Math.max(1e-15, p));
const entropy = (p: number) => p * surprise(p) + (1 - p) * surprise(1 - p);

/** Read-only analysis of checksummed, schema-validated production operations.
 * Uses the designated primary receipt once per game, never all forecast snapshots.
 * The same completed subset supplies both observed and expected quantities.
 */
export function weeklyIntelligence(operations: Operations, week: number) {
  const records = new Map(operations.catalog.map(f => [f.id, f]));
  const games = new Map(operations.games.filter(g => g.week === week).map(g => [g.id, g]));
  const schedule = new Map(operations.schedule.filter(g => g.week === week).map(g => [g.id, g]));
  const ids = new Set([...schedule.keys(), ...games.keys()]);
  const eligible = (f: ForecastRecord | undefined, id: string) => !!f && f.game_id === id
    && f.season === operations.season && f.week === week && f.eligible && !f.exclusions.length
    && f.forecast_status === "available" && f.kickoff !== null
    && Date.parse(f.generated_at) < Date.parse(f.kickoff)
    && f.home_probability !== null && f.away_probability !== null;
  const eligibleGames = new Set(operations.catalog.filter(f => eligible(f, f.game_id)).map(f => f.game_id));
  const rows: { game: Operations["games"][number]; forecast: ForecastRecord; pickProbability: number;
    realizedProbability: number; winner: string; correct: boolean; surprise: number }[] = [];
  let pending = 0, ties = 0, missing = 0, held = 0, unscored = 0;
  let unfinished = false;
  for (const id of ids) {
    const g = games.get(id), status = g?.status ?? schedule.get(id)?.status;
    if (status !== "completed" && status !== "canceled") unfinished = true;
    if (status === "postponed" || status === "canceled") { held++; continue; }
    if (!eligibleGames.has(id)) { missing++; continue; }
    if (!g?.result || status !== "completed") { pending++; continue; }
    if (g.result.tie) { ties++; continue; }
    const f = records.get(g.final_forecast_id ?? "");
    if (!eligible(f, id) || !f?.selected_final || !g.evaluations.some(e => e.primary && e.forecast_id === f.id)) {
      unscored++; continue;
    }
    const p = f.home_probability!;
    const homeWon = g.result.home_score > g.result.away_score;
    const realizedProbability = homeWon ? p : 1 - p;
    rows.push({ game: g, forecast: f, pickProbability: Math.max(p, 1 - p), realizedProbability,
      winner: homeWon ? g.home : g.away, correct: (p >= .5) === homeWon, surprise: surprise(realizedProbability) });
  }
  // Stable order makes results reproducible even when an artifact's arrays are reordered.
  rows.sort((a, b) => a.game.id.localeCompare(b.game.id));
  const count = rows.length, correct = rows.filter(r => r.correct).length;
  const distribution = poissonBinomial(rows.map(r => r.pickProbability));
  const sum = (values: number[]) => values.reduce((a, b) => a + b, 0);
  const expected = count ? sum(rows.map(r => r.pickProbability)) : null;
  const totalSurprise = count ? sum(rows.map(r => r.surprise)) : null;
  return { week, season: operations.season, total: ids.size, count, correct, pending, ties, missing, held, unscored,
    partial: unfinished || pending > 0, expected, difference: expected === null ? null : correct - expected,
    distribution, lowerTail: count ? Math.min(1, sum(distribution.slice(0, correct + 1))) : null,
    totalSurprise, meanSurprise: totalSurprise === null ? null : totalSurprise / count,
    expectedSurprise: count ? sum(rows.map(r => entropy(r.forecast.home_probability!))) : null,
    rows, upsets: rows.filter(r => r.realizedProbability < .5)
      .sort((a, b) => a.realizedProbability - b.realizedProbability || a.game.id.localeCompare(b.game.id)),
  };
}
