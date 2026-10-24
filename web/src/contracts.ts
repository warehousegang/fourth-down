import { z } from "zod";
const finite = z.number().finite();
const probability = finite.min(0).max(1);
const count = z.number().int().nonnegative();
const timestamp = z.string().datetime({ offset: true });
const metric = z.object({
  n: count,
  accuracy: probability,
  brier: probability,
  log_loss: finite.nonnegative(),
});
const factor = z.object({
  key: z.string(),
  label: z.string(),
  home: finite,
  away: finite,
  difference: finite,
  coefficient: finite,
  contribution: finite,
});
const game = z.object({
  id: z.string(),
  season: z.literal(2023),
  week: count.min(1).max(18),
  home: z.string(),
  away: z.string(),
  kickoff: timestamp.nullable(),
  cutoff: timestamp,
  stadium: z.string(),
  neutral_site: z.boolean(),
  history_games: z.object({ home: count, away: count }),
  model_id: z.string(),
  status: z.enum(["available", "unavailable"]),
  reason: z.string().nullable(),
  home_probability: probability.nullable(),
  factors: z.array(factor),
});
export const artifactSchema = z
  .object({
    schema_version: z.literal(1),
    mode: z.literal("historical-replay"),
    generated_at: timestamp,
    model: z.object({
      id: z.string(),
      name: z.string(),
      kind: z.enum(["coin", "home", "original", "schedule"]),
      features: z.array(z.string()),
      coefficients: z.array(finite),
      intercept: finite,
      feature_version: z.string(),
      source_sha256: z.string().regex(/^[a-f0-9]{64}$/),
      train_seasons: z.tuple([z.literal(2010), z.literal(2022)]),
      seed: z.number().int(),
    }),
    evaluation: z.object({
      generated_at: timestamp,
      source: z.object({
        source: z.string().url(),
        retrieved_at: timestamp,
        sha256: z.string(),
        rows: count,
        python: z.string(),
        packages: z.record(z.string(), z.string()),
        seasons: z.tuple([z.literal(2010), z.literal(2023)]),
      }),
      feature_version: z.string(),
      train_n: count,
      validation_n: count,
      train_seasons: z.tuple([z.literal(2010), z.literal(2022)]),
      validation_season: z.literal(2023),
      home_win_rate: probability,
      selected: z.string(),
      models: z.array(metric.extend({ id: z.string(), name: z.string() })),
      ablations: z.array(metric.extend({ removed: z.string() })),
      backtests: z.array(
        z.object({
          season: z.number().int().min(2018).max(2022),
          train_n: count,
          model: metric,
          baseline: metric,
        }),
      ),
      calibration: z.array(
        z.object({
          bin: count.max(9),
          count: count.min(1),
          predicted: probability,
          observed: probability,
        }),
      ),
      brier_difference: z.object({
        mean: finite,
        low: finite,
        high: finite,
        unit: z.literal("week"),
        replicates: count,
      }),
      holdout_status: z.literal("locked"),
      original_feature_parity: z.literal(true),
      selection_rule: z.string(),
    }),
    games: z.array(game).max(300),
    attribution: z.object({
      name: z.string(),
      url: z.string().url(),
      license: z.string(),
      license_url: z.string().url(),
    }),
    limitations: z.array(z.string()),
  })
  .superRefine((data, ctx) => {
    const fail = (message: string) => ctx.addIssue({ code: "custom", message });
    const m = data.model;
    const expectedModels = ["coin", "home", "original", "schedule"];
    if (
      data.evaluation.models.length !== expectedModels.length ||
      expectedModels.some(id => data.evaluation.models.filter(x => x.id === id).length !== 1)
    ) fail("Required baseline comparison is missing or duplicated");
    if (
      m.features.length !== m.coefficients.length ||
      new Set(m.features).size !== m.features.length
    )
      fail("Invalid coefficient dimensions");
    if (
      m.source_sha256 !== data.evaluation.source.sha256 ||
      m.kind !== data.evaluation.selected ||
      m.feature_version !== data.evaluation.feature_version
    )
      fail("Model/evaluation lineage mismatch");
    if (
      !data.evaluation.models.some((x) => x.id === m.kind) ||
      data.evaluation.models.some((x) => x.n !== data.evaluation.validation_n)
    )
      fail("Inconsistent evaluation observations");
    if (new Set(data.games.map((g) => g.id)).size !== data.games.length)
      fail("Duplicate games");
    if (
      data.evaluation.calibration.reduce((n, b) => n + b.count, 0) !==
      data.evaluation.validation_n
    )
      fail("Calibration count mismatch");
    for (const g of data.games) {
      if (g.home === g.away) fail("A team cannot play itself");
      if (g.model_id !== m.id) fail("Game/model version mismatch");
      if (g.kickoff && new Date(g.cutoff) >= new Date(g.kickoff))
        fail("Invalid forecast cutoff");
      if (g.status === "unavailable") {
        if (g.home_probability !== null || !g.reason || g.factors.length)
          fail("Unavailable forecast must have a reason and no probability");
        continue;
      }
      if (
        g.home_probability === null ||
        g.factors.length !== m.features.length
      ) {
        fail("Missing probability or factors");
        continue;
      }
      let logOdds = m.intercept;
      g.factors.forEach((f, i) => {
        if (f.key !== m.features[i] || f.coefficient !== m.coefficients[i])
          fail("Factor/model mismatch");
        if (
          Math.abs(f.home - f.away - f.difference) > 1e-9 ||
          Math.abs(f.difference * f.coefficient - f.contribution) > 1e-9
        )
          fail("Factor arithmetic mismatch");
        logOdds += f.contribution;
      });
      if (Math.abs(1 / (1 + Math.exp(-logOdds)) - g.home_probability) > 1e-9)
        fail("Probability does not match model explanation");
    }
  });
export type Artifact = z.infer<typeof artifactSchema>;
export type Game = Artifact["games"][number];
export async function loadArtifact(): Promise<Artifact> {
  const response = await fetch(`${import.meta.env.BASE_URL}data/demo.json`);
  if (!response.ok)
    throw new Error(
      "The forecast artifact could not be loaded. Generate the local demo data and try again.",
    );
  const text = await response.text();
  if (text.length > 2_000_000)
    throw new Error("Forecast artifact exceeds the allowed size.");
  const parsed = artifactSchema.safeParse(JSON.parse(text));
  if (!parsed.success)
    throw new Error(
      "Forecast data failed validation. No probabilities are displayed. Regenerate the artifact from the verified pipeline.",
    );
  return parsed.data;
}
