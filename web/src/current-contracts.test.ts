import { describe, it, expect, vi, afterEach } from "vitest";
import { webcrypto } from "node:crypto";
import { currentSchema, loadCurrent, unavailableReason } from "./current-contracts";
import { currentFixture, currentPointer, currentText } from "./current-fixture";

afterEach(() => vi.unstubAllGlobals());
describe("current artifact integrity", () => {
  it("validates the real frozen-model current forecast", () => {
    const d = currentFixture();
    expect(d.mode).toBe("current-forecast");
    expect(d.season).toBeGreaterThanOrEqual(2026);
    expect(d.games.some(g => g.status === "available")).toBe(true);
  });
  it.each(["coefficient", "probability", "feature", "history", "season", "cutoff"])("rejects %s tampering", field => {
    const d = currentFixture(), g = d.games.find(g => g.status === "available")!;
    if (field === "coefficient") d.model.coefficients[0] += .01;
    if (field === "probability") g.home_probability = .99;
    if (field === "feature") g.factors[0].home += .1;
    if (field === "history") g.history.home[0].observed_at = g.kickoff!;
    if (field === "season") g.season = 2025;
    if (field === "cutoff") g.cutoff = g.kickoff!;
    expect(currentSchema.safeParse(d).success).toBe(false);
  });
  it("requires unavailable games to have no probability or factors", () => {
    const d = currentFixture();
    d.games[0].status = "unavailable";
    expect(currentSchema.safeParse(d).success).toBe(false);
  });
  it("suppresses expired and past-kickoff predictions", () => {
    const d = currentFixture(), g = d.games[0];
    expect(unavailableReason(d,g,Date.parse(d.valid_until)+1)).toMatch(/expired/);
    d.valid_until = new Date(Date.parse(g.kickoff!)+1000).toISOString();
    expect(unavailableReason(d,g,Date.parse(g.kickoff!))).toMatch(/Kickoff has passed/);
  });
  it("loads the pointer and verifies exact bytes", async () => {
    vi.stubGlobal("crypto", webcrypto);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(currentPointer))).mockResolvedValueOnce(new Response(currentText)));
    const result = await loadCurrent();
    expect(result.sha256).toBe(currentPointer.sha256);
  });
  it("fails closed on corrupt bytes and unsafe pointer paths", async () => {
    vi.stubGlobal("crypto", webcrypto);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(currentPointer))).mockResolvedValueOnce(new Response(currentText+" ")));
    await expect(loadCurrent()).rejects.toThrow(/integrity/);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({...currentPointer,file:"../demo.json"}))));
    await expect(loadCurrent()).rejects.toThrow(/integrity/);
  });
});

it("rejects an available forecast generated at or after kickoff", () => {
  const data = currentFixture();
  const first = data.games.find(g=>g.status==="available")!;
  data.games=[first];
  data.generated_at=first.kickoff!;
  first.generated_at=data.generated_at;
  expect(currentSchema.safeParse(data).success).toBe(false);
});
it("retains strict-before ordering for observations within one millisecond",()=>{
  const d=currentFixture();const g=d.games[0];d.games=[g];g.cutoff="2026-10-24T13:38:08.054002Z";g.history.home[0].observed_at="2026-10-24T13:38:08.054001Z";
  expect(currentSchema.safeParse(d).success).toBe(true);
  g.history.home[0].observed_at=g.cutoff;expect(currentSchema.safeParse(d).success).toBe(false);
});
it("rejects a fractional instant after the frozen midnight cutoff",()=>{
  const d=currentFixture();const g=d.games[0];d.games=[g];d.as_of="2026-10-25T04:00:00.000001Z";d.generated_at=d.as_of;g.generated_at=d.generated_at;g.cutoff=d.as_of;expect(currentSchema.safeParse(d).success).toBe(false);
});
