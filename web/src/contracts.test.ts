import { describe, it, expect } from "vitest";
import { artifactSchema } from "./contracts";
import demo from "../public/data/demo.json";
// This import is relative to src; Vite resolves the actual production artifact.
describe("forecast artifact contract", () => {
  it("rejects an artifact missing the baseline the interface compares against", () => {
    const bad = structuredClone(demo);
    bad.evaluation.models = bad.evaluation.models.filter(m => m.id !== "home");
    expect(artifactSchema.safeParse(bad).success).toBe(false);
  });
  it("accepts the real Python artifact and all model-derived explanations", () => {
    expect(artifactSchema.parse(demo).games).toHaveLength(272);
  });
  it.each([
    "probability",
    "contribution",
    "lineage",
    "holdout",
    "duplicate",
    "cutoff",
  ])("rejects tampered %s", (kind) => {
    const bad = structuredClone(demo);
    if (kind === "probability") bad.games[0].home_probability = 0.123456;
    if (kind === "contribution") bad.games[0].factors[0].contribution = 3;
    if (kind === "lineage") bad.games[0].model_id = "other";
    if (kind === "holdout") bad.games[0].season = 2024;
    if (kind === "duplicate") bad.games.push(bad.games[0]);
    if (kind === "cutoff") bad.games[0].cutoff = "2026-10-24T00:00:00Z";
    expect(artifactSchema.safeParse(bad).success).toBe(false);
  });
  it("requires a real unavailable state", () => {
    const unavailable = structuredClone(demo) as unknown as Record<string, any>;
    Object.assign(unavailable.games[0], {
      status: "unavailable",
      reason: "Required feature missing",
      home_probability: null,
      factors: [],
    });
    expect(artifactSchema.safeParse(unavailable).success).toBe(true);
  });
});
