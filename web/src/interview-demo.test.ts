import { expect, it } from "vitest";
import { demonstrationForecasts, researchWalkthrough, simulateBernoulli } from "./interview-demo";
import { operationsFixture } from "./intelligence-fixtures";

it.each([0, .5, .8, 1])("samples p=%s reproducibly with conditional uncertainty", p => {
  const result = simulateBernoulli(p, 100_000, 42);
  expect(result).toEqual(simulateBernoulli(p, 100_000, 42));
  expect(result.wins + result.losses).toBe(100_000);
  expect(result.standardError).toBe(Math.sqrt(p * (1 - p) / 100_000));
  if (p === 0 || p === 1) expect(result.frequency).toBe(p);
  else expect(Math.abs(result.frequency - p)).toBeLessThan(.006);
  expect(result).not.toHaveProperty("accuracy");
  expect(result).not.toHaveProperty("score");
});
it("supports boundary seeds and independent seeded streams", () => {
  expect(simulateBernoulli(.5, 1000, 0)).not.toEqual(simulateBernoulli(.5, 1000, 0xffffffff));
  expect(simulateBernoulli(.5, 1, 1).wins).toBe(0); // First Mulberry32 draw for seed 1 is 0.6270739405881613.
});
it.each([NaN, Infinity, -Infinity, -0.01, 1.01, true, "0.5", null])("rejects invalid probability %s", p => {
  expect(() => simulateBernoulli(p as number, 100, 42)).toThrow(/Probability/);
});
it.each([0, -1, 1.5, 100_001, NaN, Infinity, true])("rejects invalid count %s", count => {
  expect(() => simulateBernoulli(.5, count as number, 42)).toThrow(/draw count/);
});
it.each([-1, 1.5, 0x100000000, NaN, Infinity, true])("rejects invalid seed %s", seed => {
  expect(() => simulateBernoulli(.5, 100, seed as number)).toThrow(/seed/);
});
it("selects only a matching eligible future latest record without mutating the evidence", () => {
  const data = operationsFixture();
  const before = JSON.stringify(data);
  const now = Date.parse(data.generated_at);
  const records = demonstrationForecasts(data, now);
  expect(records.length).toBeGreaterThan(0);
  expect(records.every(f => f.latest && f.eligible)).toBe(true);
  const record = records[0];
  expect(demonstrationForecasts(data, Date.parse(record.kickoff!)).some(f => f.id === record.id)).toBe(false);
  expect(demonstrationForecasts(data, now - 1)).toEqual([]);
  expect(demonstrationForecasts(data, NaN)).toEqual([]);
  // Expiry is disclosed in the UI; an archived estimate remains a valid synthetic input before kickoff.
  record.valid_until = new Date(now - 1).toISOString();
  expect(demonstrationForecasts(data, now).some(f => f.id === record.id)).toBe(true);
  record.valid_until = operationsFixture().catalog.find(f => f.id === record.id)!.valid_until;
  expect(JSON.stringify(data)).toBe(before);
  data.schedule.find(g => g.id === record.game_id)!.status = "postponed";
  expect(demonstrationForecasts(data, now).some(f => f.id === record.id)).toBe(false);
});
it("rejects an unavailable, mismatched or excluded saved input", () => {
  for (const mutate of [
    (f: ReturnType<typeof operationsFixture>["catalog"][number]) => { f.eligible = false; },
    (f: ReturnType<typeof operationsFixture>["catalog"][number]) => { f.home_probability = null; },
    (f: ReturnType<typeof operationsFixture>["catalog"][number]) => { f.exclusions.push("Missing source evidence"); },
    (f: ReturnType<typeof operationsFixture>["catalog"][number]) => { f.kickoff = "2026-12-30T20:00:00Z"; },
  ]) {
    const data = operationsFixture(); const now = Date.parse(data.generated_at);
    const f = demonstrationForecasts(data, now)[0]; mutate(f);
    expect(demonstrationForecasts(data, now).some(row => row.id === f.id)).toBe(false);
  }
});
it("creates a deterministic proposal from saved factors without creating findings or edits", () => {
  const data = operationsFixture();
  const f = demonstrationForecasts(data, Date.parse(data.generated_at))[0];
  const before = JSON.stringify(f);
  const walkthrough = researchWalkthrough(f);
  expect(walkthrough).toEqual(researchWalkthrough(f));
  expect(walkthrough.plan).toContain(`${f.away} at ${f.home}`);
  expect(walkthrough.hypothesis).toContain("not an established effect");
  expect(walkthrough.evidenceNeeded).toContain("No new experiment has been run");
  expect(walkthrough.proposal).toContain("2024–2025 holdout remains locked");
  expect(JSON.stringify(f)).toBe(before);
});
