import { expect, it } from "vitest";
import { completedFixture, operationsFixture } from "./intelligence-fixtures";
import { poissonBinomial, weeklyIntelligence } from "./weekly-intelligence";

it("convolves unequal probabilities exactly, including inclusive lower tails", () => {
  // Hand expansion: (.2 + .8z)(.4 + .6z) = .08 + .44z + .48z².
  const mass = poissonBinomial([.8, .6]);
  expect(mass).toHaveLength(3);
  [.08, .44, .48].forEach((p, i) => expect(mass[i]).toBeCloseTo(p, 14));
  expect(mass[0] + mass[1]).toBeCloseTo(.52, 14);
});
it("handles empty and certain outcomes without randomness", () => {
  expect(poissonBinomial([])).toEqual([1]);
  expect(poissonBinomial([0, 1, 1])).toEqual([0, 0, 1, 0]);
  expect(poissonBinomial([.5, .5, .5])).toEqual([.125, .375, .375, .125]);
});
it.each([-0.1, 1.1, NaN, Infinity])("rejects invalid probability %s", p => {
  expect(() => poissonBinomial([p])).toThrow(RangeError);
});
it("matches independent enumeration across a full 16-game slate", () => {
  const ps = Array.from({length:16}, (_, i) => .51 + i * .025);
  const enumerated = Array(17).fill(0);
  for (let mask=0; mask<2**16; mask++) {
    let probability=1, count=0;
    for (let i=0; i<16; i++) { const won=!!(mask & (1<<i)); count+=Number(won); probability*=won?ps[i]:1-ps[i]; }
    enumerated[count]+=probability;
  }
  const mass=poissonBinomial(ps);
  mass.forEach((p,k)=>expect(p).toBeCloseTo(enumerated[k],12));
  expect(mass.reduce((s,p)=>s+p,0)).toBeCloseTo(1,14);
  expect(mass.reduce((s,p,k)=>s+p*k,0)).toBeCloseTo(ps.reduce((s,p)=>s+p,0),13);
});
it("uses the designated archived prediction exactly once, and never mutates evidence", () => {
  const ops=completedFixture(24,17), before=JSON.stringify(ops);
  const f=ops.catalog.find(f=>f.selected_final)!;
  const s=weeklyIntelligence(ops,7);
  expect(s.count).toBe(1); expect(s.correct).toBe(0);
  expect(s.expected).toBe(1-f.home_probability!);
  expect(s.lowerTail).toBeCloseTo(f.home_probability!,14);
  expect(s.totalSurprise).toBeCloseTo(-Math.log(f.home_probability!),14);
  expect(s.meanSurprise).toBe(ops.metrics.primary.log_loss);
  expect(s.difference).toBe(-s.expected!);
  expect(s.rows[0].forecast.generated_at).toBe(f.generated_at);
  expect(JSON.stringify(ops)).toBe(before);
});
it("recomputes corrections idempotently from the same immutable forecast", () => {
  const wrong=completedFixture(24,17), right=completedFixture(17,24);
  const a=weeklyIntelligence(wrong,7), b=weeklyIntelligence(right,7);
  expect(b.correct).toBe(1); expect(b.count).toBe(1); expect(b.lowerTail).toBeCloseTo(1,14);
  expect(a.expected).toBe(b.expected); expect(a.distribution).toEqual(b.distribution);
  expect(a.rows[0].forecast).toEqual(b.rows[0].forecast);
  expect(b).toEqual(weeklyIntelligence(right,7));
});
it("keeps weekly and completed subsets separate, including schedule-only missing predictions", () => {
  const ops=operationsFixture(), s=weeklyIntelligence(ops,7);
  expect(s.count).toBe(0); expect(s.pending).toBe(13); expect(s.missing).toBe(1); expect(s.total).toBe(14);
  expect(s.expected).toBeNull(); expect(s.lowerTail).toBeNull(); expect(s.meanSurprise).toBeNull();
  const final=completedFixture();
  expect(weeklyIntelligence(final,8).count).toBe(0);
  expect(weeklyIntelligence(final,7).partial).toBe(true);
});
it("excludes ties, unverified finals, missing designations and non-primary snapshots", () => {
  const tie=weeklyIntelligence(completedFixture(24,24),7);
  expect(tie.count).toBe(0); expect(tie.ties).toBe(1);
  const ops=completedFixture(); ops.games[0].result=null;
  expect(weeklyIntelligence(ops,7).pending).toBe(1);
  expect(weeklyIntelligence(ops,7).count).toBe(0);
  const noPrimary=completedFixture(); noPrimary.games[0].evaluations.forEach(e=>{e.primary=false});
  expect(weeklyIntelligence(noPrimary,7).unscored).toBe(1);
  noPrimary.games[0].final_forecast_id=null;
  expect(weeklyIntelligence(noPrimary,7).count).toBe(0);
});
it.each(["postponed", "canceled"] as const)("keeps %s games out of the sample", status => {
  const ops=completedFixture(); ops.games[0].status=status;
  const s=weeklyIntelligence(ops,7);
  expect(s.count).toBe(0); expect(s.held).toBe(1); expect(s.pending).toBe(0);
});
it("rejects a receipt generated at kickoff even if erroneously marked eligible", () => {
  const ops=completedFixture(); ops.catalog.forEach(f=>{f.generated_at=f.kickoff!});
  const s=weeklyIntelligence(ops,7); expect(s.count).toBe(0); expect(s.rows).toEqual([]);
});
it("uses the existing 50% home-pick convention without labeling a coin flip an upset", () => {
  const ops=completedFixture(17,24), f=ops.catalog.find(f=>f.selected_final)!;
  f.home_probability=f.away_probability=.5;
  const s=weeklyIntelligence(ops,7);
  expect(s.correct).toBe(0); expect(s.expected).toBe(.5); expect(s.lowerTail).toBe(.5); expect(s.upsets).toEqual([]);
  expect(s.totalSurprise).toBe(Math.log(2)); expect(s.expectedSurprise).toBe(Math.log(2));
});
it("uses the existing log floor at zero without rewriting probabilities", () => {
  const ops=completedFixture(24,17), f=ops.catalog.find(f=>f.selected_final)!;
  f.home_probability=0; f.away_probability=1;
  const s=weeklyIntelligence(ops,7);
  expect(s.lowerTail).toBe(0); expect(s.totalSurprise).toBe(-Math.log(1e-15)); expect(f.home_probability).toBe(0);
});
