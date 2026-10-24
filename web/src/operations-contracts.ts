import { z } from "zod";
import frozen from "../../docs/FROZEN_MODEL.json";
import { compareTimestamp, count, digest, finite, loadVersioned, probability, sourceURL, timestamp } from "./versioned-artifact";

const nullableMetric = probability.nullable();
const status = z.enum(["scheduled", "postponed", "canceled", "in_progress", "completed", "unknown"]);
const score = z.object({ brier: probability, log_loss: finite.nonnegative(), correct: z.boolean() });
const aggregate = z.object({ count, accuracy: nullableMetric, brier: nullableMetric, log_loss: finite.nonnegative().nullable() });
const calibration = z.object({ lower: probability, upper: probability, count, mean_probability: nullableMetric, home_win_rate: nullableMetric, brier: nullableMetric });
const metricSet = aggregate.extend({ game_count: count, ties_excluded: count,
  baselines: z.object({ coin_flip: aggregate, home_rate: aggregate }),
  by_season: z.array(aggregate.extend({ season: z.number().int().min(2026) }).passthrough()),
  calibration: z.array(calibration).length(10),
});
const history = z.array(z.object({ id: z.string(), game_day: z.string(), observed_at: timestamp, snapshot_sha256: digest }));
const catalog = z.object({
  id: digest, game_id: z.string(), season: z.number().int().min(2026),
  artifact_file: z.string().regex(/^forecast-20\d{2}-[a-f0-9]{64}\.json$/), artifact_sha256: digest,
  generated_at: timestamp, cutoff: timestamp, kickoff: timestamp.nullable(), valid_until: timestamp,
  home: z.string(), away: z.string(), model_id: z.literal(frozen.model.id), features: z.record(z.string(), finite),
  home_probability: probability.nullable(), away_probability: probability.nullable(),
  forecast_status: z.enum(["available", "unavailable"]), eligible: z.boolean(), exclusions: z.array(z.string()),
  selected_final: z.boolean(), latest: z.boolean(),
  factors: z.array(z.object({ key: z.string(), label: z.string(), home: finite, away: finite, difference: finite, coefficient: finite, contribution: finite })),
  history: z.object({ home: history, away: history }),
});
const evaluation = z.object({ forecast_id: digest, primary: z.boolean(), home_probability: probability,
  outcome_home: z.union([z.literal(0), z.literal(1)]), correct: z.boolean(), brier: probability, log_loss: finite.nonnegative(), surprise: finite.nonnegative(),
  baseline: z.object({ coin_flip: score, home_rate: score.extend({ probability }) }),
});
export const operationsSchema = z.object({
  schema_version: z.literal(1), mode: z.literal("forecast-operations"), season: z.number().int().min(2026), generated_at: timestamp,
  model_id: z.literal(frozen.model.id), protocol: z.object({ version: z.string(), sha256: digest }),
  source: z.object({ snapshot_sha256: digest, retrieved_at: timestamp, source_updated_at: timestamp, source_url: sourceURL, raw_sha256: digest }),
  schedule: z.array(z.object({ id: z.string(), season: z.number().int().min(2026), week: count.min(1).max(18), home: z.string(), away: z.string(), kickoff: timestamp.nullable(), day: z.string().nullable(), stadium: z.string(), status, source_phase: z.string() })).max(300),
  catalog: z.array(catalog).max(10000),
  games: z.array(z.object({ id: z.string(), home: z.string(), away: z.string(), week: count.min(1).max(18), kickoff: timestamp.nullable(), status,
    forecast_ids: z.array(digest), original_forecast_id: digest.nullable(), latest_forecast_id: digest.nullable(), final_forecast_id: digest.nullable(),
    result: z.object({ version: z.string(), home_score: count, away_score: count, tie: z.boolean(), observed_at: timestamp, source_url: sourceURL, snapshot_sha256: digest }).nullable(),
    evaluations: z.array(evaluation), analysis: z.object({ facts: z.array(z.object({ text: z.string(), source_url: sourceURL, observed_at: timestamp })), hypotheses: z.array(z.object({ text: z.string(), evidence_needed: z.string() })), deficiencies: z.array(z.string()) }).nullable(),
  })).max(300),
  metrics: z.object({ primary: metricSet, all_snapshots: metricSet }), warnings: z.array(z.string()), limitations: z.array(z.string()),
}).superRefine((data, ctx) => {
  const fail = (message: string) => ctx.addIssue({ code: "custom", message });
  const close = (a: number | null, b: number | null) => a === null || b === null ? a === b : Math.abs(a-b) < 1e-9;
  if (compareTimestamp(data.source.source_updated_at, data.source.retrieved_at) > 0 || compareTimestamp(data.source.retrieved_at, data.generated_at) > 0) fail("Invalid operations time ordering");
  if (!data.source.source_url.endsWith(`/ngs_schedule_${data.season}.csv`)) fail("Operations source season mismatch");
  const snapshots = new Map(data.catalog.map(f => [f.id, f]));
  const schedule = new Map(data.schedule.map(g => [g.id, g]));
  if (snapshots.size !== data.catalog.length || schedule.size !== data.schedule.length || new Set(data.games.map(g => g.id)).size !== data.games.length) fail("Duplicate operations records");
  for (const game of data.schedule) if (game.season !== data.season || !game.id.startsWith(`ngs-${data.season}-`) || game.home === game.away) fail("Invalid schedule lineage");
  for (const f of data.catalog) {
    if (f.season !== data.season || !f.game_id.startsWith(`ngs-${data.season}-`) || f.artifact_file !== `forecast-${data.season}-${f.artifact_sha256}.json` || f.eligible && !schedule.has(f.game_id)) fail("Invalid forecast lineage");
    if (compareTimestamp(f.cutoff, f.generated_at) > 0 || compareTimestamp(f.generated_at, data.generated_at) > 0) fail("Invalid forecast ordering");
    if (f.eligible && (f.forecast_status !== "available" || f.exclusions.length || !f.kickoff || compareTimestamp(f.generated_at, f.kickoff) >= 0)) fail("Ineligible forecast marked eligible");
    if (!f.eligible && !f.exclusions.length) fail("Ineligible forecast lacks an explanation");
    if (f.forecast_status === "unavailable") {
      if (f.home_probability !== null || f.away_probability !== null || f.factors.length || Object.keys(f.features).length) fail("Unavailable archive forecast has a probability");
    } else {
      if (f.home_probability === null || f.away_probability === null || f.factors.length !== 4 || Object.keys(f.features).length !== 4) { fail("Missing archive model inputs"); continue; }
      let odds = frozen.model.intercept;
      frozen.model.features.forEach((name, i) => {
        const factor = f.factors[i];
        const value = f.features[name];
        if (value === undefined || !factor || factor.key !== name || factor.coefficient !== frozen.model.coefficients[i] || !close(factor.home-factor.away, value) || !close(factor.difference,value) || !close(factor.contribution,value*frozen.model.coefficients[i])) fail("Archive feature arithmetic mismatch");
        odds += value * frozen.model.coefficients[i];
      });
      if (!close(f.home_probability,1/(1+Math.exp(-odds))) || !close(f.home_probability+f.away_probability,1)) fail("Archive probability differs from frozen model");
      for (const side of ["home", "away"] as const) for (const h of f.history[side]) if (!h.id.startsWith(`ngs-${data.season}-`) || h.id === f.game_id || compareTimestamp(h.observed_at,f.cutoff)>=0) fail("Archive history includes future information");
    }
  }
  const all: z.infer<typeof evaluation>[] = [];
  let ties = 0, tiesAll = 0;
  for (const g of data.games) {
    const current = schedule.get(g.id);
    if (current ? current.home !== g.home || current.away !== g.away || current.status !== g.status : g.status !== "unknown" || g.result !== null || g.evaluations.length > 0 || g.final_forecast_id !== null) fail("Game does not match observed schedule");
    const records = g.forecast_ids.map(id=>snapshots.get(id));
    if (new Set(g.forecast_ids).size !== g.forecast_ids.length || records.some(f=>!f || f.game_id!==g.id)) fail("Game/archive mismatch");
    if (g.original_forecast_id && !g.forecast_ids.includes(g.original_forecast_id)) fail("Original forecast missing");
    if (g.latest_forecast_id && (!g.forecast_ids.includes(g.latest_forecast_id) || !snapshots.get(g.latest_forecast_id)?.latest)) fail("Latest forecast mismatch");
    if (g.final_forecast_id && (!g.forecast_ids.includes(g.final_forecast_id) || !snapshots.get(g.final_forecast_id)?.selected_final || !snapshots.get(g.final_forecast_id)?.eligible || !g.kickoff || compareTimestamp(g.kickoff,data.generated_at)>0)) fail("Invalid final pregame forecast");
    if (g.result) {
      if (g.status !== "completed" || g.result.tie !== (g.result.home_score === g.result.away_score) || compareTimestamp(g.result.observed_at,data.generated_at)>0 || !g.kickoff || compareTimestamp(g.result.observed_at,g.kickoff)<=0) fail("Unverified result");
      if (g.result.tie) { if(g.final_forecast_id)ties++; tiesAll+=records.filter(f=>f?.eligible).length; }
    }
    if(g.analysis)for(const fact of g.analysis.facts)if(compareTimestamp(fact.observed_at,data.generated_at)>0)fail("Future-dated analysis evidence");
    if (g.evaluations.length && (!g.result || g.result.tie)) fail("Evaluation lacks a non-tied result");
    if (new Set(g.evaluations.map(e=>e.forecast_id)).size !== g.evaluations.length) fail("Duplicate outcome evaluation");
    for (const e of g.evaluations) {
      const f = snapshots.get(e.forecast_id);
      const y = g.result && g.result.home_score>g.result.away_score ? 1 : 0;
      // Preserved demo.json evaluation.home_win_rate from the 2010–2022 training population.
      if(e.baseline.home_rate.probability !== 0.5572154167911563)fail("Baseline differs from the preserved training home rate");
      const p = e.home_probability;
      const actualP = y ? p : 1-p;
      if (!f?.eligible || f.game_id!==g.id || f.home_probability!==p || e.outcome_home!==y || e.primary!==(g.final_forecast_id===e.forecast_id)) fail("Evaluation/forecast lineage mismatch");
      if (e.correct!==((p>=0.5 ? 1 : 0)===y) || !close(e.brier,(p-y)**2) || !close(e.log_loss,-Math.log(Math.max(1e-15,actualP))) || !close(e.surprise,-Math.log(Math.max(1e-15,actualP)))) fail("Incorrect outcome scores");
      for (const [name,b] of Object.entries(e.baseline)) {
        const bp = name === "coin_flip" ? .5 : e.baseline.home_rate.probability;
        if (!close(b.brier,(bp-y)**2) || !close(b.log_loss,-Math.log(y ? bp : 1-bp)) || b.correct!==((bp>=.5 ? 1 : 0)===y)) fail("Incorrect baseline score");
      }
      all.push(e);
    }
  }
  function checkMetrics(m: z.infer<typeof metricSet>, rows: typeof all, primary: boolean) {
    const mean = (values: number[]) => values.length ? values.reduce((a,b)=>a+b,0)/values.length : null;
    const check = (actual: z.infer<typeof aggregate>, items: { correct: boolean; brier: number; log_loss: number }[]) => {
      if (actual.count!==items.length || !close(actual.accuracy,mean(items.map(e=>Number(e.correct)))) || !close(actual.brier,mean(items.map(e=>e.brier))) || !close(actual.log_loss,mean(items.map(e=>e.log_loss)))) fail("Aggregate score mismatch");
    };
    check(m, rows);
    if (m.game_count!==new Set(rows.map(e=>snapshots.get(e.forecast_id)?.game_id)).size || (m.ties_excluded!==(primary?ties:tiesAll))) fail("Metric population mismatch");
    check(m.baselines.coin_flip,rows.map(e=>e.baseline.coin_flip));
    check(m.baselines.home_rate,rows.map(e=>e.baseline.home_rate));
    if (m.by_season.length !== (rows.length ? 1 : 0)) fail("Season metric population mismatch");
    for (const season of m.by_season) { if(season.season!==data.season) fail("Protected season in metrics"); check(season,rows); }
    let countBins = 0;
    for (const [bin,b] of m.calibration.entries()) {
      if(b.lower!==bin/10 || b.upper!==(bin+1)/10)fail("Invalid calibration boundaries");
      const selected = rows.filter(e=>e.home_probability>=b.lower && (e.home_probability<b.upper || b.upper===1 && e.home_probability===1));
      if (!(b.lower<b.upper) || b.count!==selected.length || !close(b.mean_probability,mean(selected.map(e=>e.home_probability))) || !close(b.home_win_rate,mean(selected.map(e=>e.outcome_home))) || !close(b.brier,mean(selected.map(e=>e.brier)))) fail("Calibration mismatch");
      countBins += b.count;
    }
    if (countBins!==rows.length) fail("Calibration population mismatch");
  }
  checkMetrics(data.metrics.primary,all.filter(e=>e.primary),true);
  checkMetrics(data.metrics.all_snapshots,all,false);
});
export type Operations = z.infer<typeof operationsSchema>;
export type ForecastRecord = Operations["catalog"][number];
export const loadOperations = () => loadVersioned("operations", "operations", operationsSchema);
