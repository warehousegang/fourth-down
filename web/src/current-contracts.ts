import { z } from "zod";
import frozen from "../../docs/FROZEN_MODEL.json";
import { compareTimestamp } from "./versioned-artifact";

const stamp = z.string().datetime({ offset: true });
const hash = z.string().regex(/^[a-f0-9]{64}$/);
const finite = z.number().finite();
const probability = finite.min(0).max(1);
const day = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
const model = z.custom<typeof frozen.model>((v) => {
  if (!v || typeof v !== "object") return false;
  return Object.entries(frozen.model).every(([k, expected]) =>
    JSON.stringify((v as Record<string, unknown>)[k]) === JSON.stringify(expected));
}, "Model differs from the frozen candidate");
const history = z.array(z.object({ id: z.string(), game_day: day, observed_at: stamp, snapshot_sha256: hash }));
export const currentSchema = z.object({
  schema_version: z.literal(1), mode: z.literal("current-forecast"),
  season: z.number().int().min(2026), week: z.number().int().min(1).max(18).nullable(),
  as_of: stamp, generated_at: stamp, valid_until: stamp, model,
  model_freeze_sha256: z.literal("2896a526ed8035b1674a6beb3c8d27c76ba4b3f466309bfeb729c6ddbf80f957"),
  snapshot_sha256: hash, pipeline_sha256: z.record(z.string(), hash),
  source: z.object({ source_name: z.string(), source_url: z.string().url(), raw_sha256: hash,
    source_updated_at: stamp, retrieved_at: stamp, season: z.number().int().min(2026),
    asset_id: z.number().int(), license_url: z.string().url() }),
  warnings: z.array(z.string()), limitations: z.array(z.string()),
  games: z.array(z.object({
    id: z.string(), source_game_id: z.string(), season: z.number().int().min(2026),
    week: z.number().int().min(1).max(18), home: z.string(), away: z.string(), day: day.nullable(),
    kickoff: stamp.nullable(), cutoff: stamp, generated_at: stamp, stadium: z.string(), model_id: z.string(),
    schedule_fingerprint: hash, source_phase: z.string(), status: z.enum(["available", "unavailable"]),
    reason: z.string().nullable(), home_probability: probability.nullable(), away_probability: probability.nullable(),
    features: z.record(z.string(), finite), warnings: z.array(z.string()), history: z.object({ home: history, away: history }),
    factors: z.array(z.object({ key: z.string(), label: z.string(), home: finite, away: finite,
      difference: finite, coefficient: finite, contribution: finite })),
  })).max(32),
}).superRefine((d, ctx) => {
  const fail = (message: string) => ctx.addIssue({ code: "custom", message });
  if (!(compareTimestamp(d.source.source_updated_at, d.source.retrieved_at) <= 0
    && compareTimestamp(d.source.retrieved_at, d.as_of) <= 0 && compareTimestamp(d.as_of, d.generated_at) <= 0)) fail("Invalid source/forecast ordering");
  if (Date.parse(d.valid_until) > Math.min(Date.parse(d.generated_at)+24*3600000, Date.parse(d.source.source_updated_at)+48*3600000)) fail("Invalid freshness limit");
  if (d.source.season !== d.season || d.source.source_url !== `https://github.com/sportsdataverse/sportsdataverse-data/releases/download/nfl_ngs_schedules/ngs_schedule_${d.season}.csv`) fail("Source is not isolated to forecast season");
  if (new Set(d.games.map(g => g.id)).size !== d.games.length) fail("Duplicate matchups");
  for (const g of d.games) {
    if (g.season !== d.season || !g.id.startsWith(`ngs-${d.season}-`) || g.model_id !== d.model.id || g.home === g.away) fail("Invalid matchup lineage");
    if (g.generated_at !== d.generated_at || compareTimestamp(g.cutoff, d.as_of) > 0) fail("Invalid game cutoff");
    if (g.status === "unavailable") {
      if (g.home_probability !== null || g.away_probability !== null || !g.reason || g.factors.length || Object.keys(g.features).length) fail("Unavailable forecast includes probability/features");
      continue;
    }
    if (!g.kickoff || !g.day || compareTimestamp(g.kickoff, d.generated_at) <= 0 || compareTimestamp(g.cutoff, g.kickoff) >= 0) fail("Game is not upcoming");
    if (g.day && easternTime(g.cutoff) > `${g.day}T00:00:00.000000000`) fail("After-midnight feature cutoff");
    if (g.kickoff && g.day !== easternTime(g.kickoff).slice(0, 10)) fail("Kickoff/day mismatch");
    if (!["", "SCHEDULED", "PREGAME", "PRE_GAME"].includes(g.source_phase)) fail("Game is not scheduled");
    if (g.reason !== null || g.home_probability === null || g.away_probability === null || g.factors.length !== d.model.features.length || Object.keys(g.features).length !== d.model.features.length) { fail("Missing probability/features"); continue; }
    let odds = d.model.intercept;
    g.factors.forEach((f, i) => {
      if (f.key !== d.model.features[i] || f.coefficient !== d.model.coefficients[i]
        || Math.abs(f.home-f.away-f.difference)>1e-12 || Math.abs(f.difference*f.coefficient-f.contribution)>1e-12
        || g.features[f.key] !== f.difference) fail("Feature/model arithmetic mismatch");
      odds += f.contribution;
    });
    if (Math.abs(1/(1+Math.exp(-odds))-g.home_probability)>1e-12 || Math.abs(1-g.home_probability-g.away_probability)>1e-12) fail("Probability does not match frozen model");
    for (const side of ["home", "away"] as const) {
      const records = g.history[side];
      if (new Set(records.map(r => r.id)).size !== records.length) fail("Duplicate historical game");
      for (const h of records) {
        if (!h.id.startsWith(`ngs-${d.season}-`) || h.id === g.id || !g.day || h.game_day >= g.day || compareTimestamp(h.observed_at,g.cutoff)>=0) fail("Future/current-day/cross-season history");
      }
    }
  }
});

function easternTime(value: string) {
  const parts = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", year:"numeric", month:"2-digit", day:"2-digit", hour:"2-digit", minute:"2-digit", second:"2-digit", hourCycle:"h23" }).formatToParts(new Date(value));
  const p = Object.fromEntries(parts.map(x => [x.type,x.value]));
  const fraction=(value.match(/\.(\d+)(?:Z|[+-]\d{2}:\d{2})$/)?.[1]??"").padEnd(9,"0").slice(0,9);
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}:${p.second}.${fraction}`;
}
export type CurrentArtifact = z.infer<typeof currentSchema>;
export type CurrentGame = CurrentArtifact["games"][number];
export type LoadedCurrent = { data: CurrentArtifact; file: string; sha256: string };
const pointerSchema = z.object({ schema_version: z.literal(1), file: z.string().regex(/^forecast-20\d{2}-[a-f0-9]{64}\.json$/), sha256: hash, season: z.number().int().min(2026), generated_at: stamp });
export async function loadCurrent(): Promise<LoadedCurrent> {
  const base = `${import.meta.env.BASE_URL}data/current/`;
  async function get(path: string, max: number) {
    const response = await fetch(base+path, { cache: "no-store" });
    if (!response.ok) throw new Error("No current forecast artifact is available. Run the local current-season refresh command.");
    const text = await response.text();
    if (text.length > max) throw new Error("Current artifact exceeds size limit");
    return text;
  }
  try {
    const pointer = pointerSchema.parse(JSON.parse(await get("latest.json", 2000)));
    if (pointer.file !== `forecast-${pointer.season}-${pointer.sha256}.json`) throw new Error("Version mismatch");
    const text = await get(pointer.file, 1_000_000);
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
    const actual = Array.from(new Uint8Array(digest)).map(x => x.toString(16).padStart(2,"0")).join("");
    if (actual !== pointer.sha256) throw new Error("Current artifact checksum mismatch");
    const data = currentSchema.parse(JSON.parse(text));
    if (data.season !== pointer.season || data.generated_at !== pointer.generated_at) throw new Error("Version metadata mismatch");
    return { data, file: pointer.file, sha256: actual };
  } catch (error) {
    if (error instanceof Error && error.message.startsWith("No current")) throw error;
    throw new Error("Current forecast data failed integrity validation. No probabilities are displayed; refresh from the verified pipeline.");
  }
}
