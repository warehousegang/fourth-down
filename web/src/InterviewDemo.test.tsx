import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { InterviewDemo } from "./InterviewDemo";
import { operationsFixture } from "./intelligence-fixtures";
import { demonstrationForecasts, simulateBernoulli } from "./interview-demo";

beforeEach(() => vi.spyOn(Date, "now").mockReturnValue(Date.parse(operationsFixture().generated_at)));
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });
function openDemo(data = operationsFixture()) {
  render(<InterviewDemo data={data} />);
  fireEvent.click(screen.getByText("Open simulation and research walkthrough"));
}
it("runs synthetic trials from the saved probability and reveals a cited human proposal", () => {
  const data = operationsFixture(); const f = demonstrationForecasts(data, Date.now())[0]; const before = JSON.stringify(data);
  openDemo(data);
  expect(screen.getByText(/No LLM, autonomous agent/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Run synthetic trials" }));
  const result = screen.getByRole("region", { name: "Synthetic simulation result" });
  const expected = simulateBernoulli(f.home_probability!, 10000, 42);
  expect(result).toHaveTextContent(`${expected.wins.toLocaleString("en-US")} synthetic ${f.home} wins`);
  expect(screen.getByText(/Synthetic outcomes do not validate model accuracy/)).toBeInTheDocument();
  const first = result.textContent;
  fireEvent.click(screen.getByRole("button", { name: "Run synthetic trials" }));
  expect(result.textContent).toBe(first);
  for (const name of ["Plan research", "Inspect saved inputs", "Draft hypothesis", "Prepare human proposal"]) fireEvent.click(screen.getByRole("button", { name }));
  const factors = screen.getByRole("region", { name: "Research walkthrough saved factors" });
  expect(within(factors).getAllByRole("row")).toHaveLength(5);
  expect(screen.getByRole("link", { name: "Download cited forecast inputs" })).toHaveAttribute("href", expect.stringContaining(f.artifact_file));
  expect(screen.getByText(/Human review proposal:/)).toHaveTextContent("2024–2025 holdout remains locked");
  expect(JSON.stringify(data)).toBe(before);
});
it("clears outdated results and rejects invalid controls without running trials", () => {
  openDemo(); fireEvent.click(screen.getByRole("button", { name: "Run synthetic trials" }));
  fireEvent.change(screen.getByRole("spinbutton", { name: "Simulation draws" }), { target: { value: "100001" } });
  expect(screen.queryByRole("region", { name: "Synthetic simulation result" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Run synthetic trials" }));
  expect(screen.getByRole("alert")).toHaveTextContent("1 to 100,000");
  fireEvent.change(screen.getByRole("spinbutton", { name: "Simulation draws" }), { target: { value: "1000" } });
  fireEvent.change(screen.getByRole("spinbutton", { name: "Simulation seed" }), { target: { value: "" } });
  fireEvent.click(screen.getByRole("button", { name: "Run synthetic trials" }));
  expect(screen.getByRole("alert")).toHaveTextContent("whole numbers");
});
it("resets trials and research when the selected saved matchup changes", () => {
  const data = operationsFixture(); const forecasts = demonstrationForecasts(data, Date.now()); openDemo(data);
  fireEvent.click(screen.getByRole("button", { name: "Run synthetic trials" }));
  fireEvent.click(screen.getByRole("button", { name: "Plan research" }));
  fireEvent.change(screen.getByRole("combobox", { name: "Demonstration matchup" }), { target: { value: forecasts[1].id } });
  expect(screen.queryByRole("region", { name: "Synthetic simulation result" })).not.toBeInTheDocument();
  expect(screen.queryByRole("list", { name: "Research walkthrough steps" })).not.toBeInTheDocument();
});
it("discloses expired archived probabilities and requires an actual upcoming record", () => {
  const data = operationsFixture(); data.catalog.forEach(f => { f.valid_until = new Date(Date.now() - 1).toISOString(); }); openDemo(data);
  expect(screen.getByText(/This saved forecast has expired/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Run synthetic trials" }));
  expect(screen.getByRole("region", { name: "Synthetic simulation result" })).toBeInTheDocument();
});
it("removes the demo at kickoff without leaving a synthetic result visible", async () => {
  vi.restoreAllMocks(); vi.useFakeTimers();
  const data = operationsFixture(); const now = Date.parse(data.generated_at); vi.setSystemTime(now);
  const f = demonstrationForecasts(data, now)[0]; const game = data.games.find(g => g.id === f.game_id)!;
  data.games = [game]; const kickoff = new Date(now + 100).toISOString();
  f.kickoff = kickoff; game.kickoff = kickoff; data.schedule.find(g => g.id === game.id)!.kickoff = kickoff;
  openDemo(data); fireEvent.click(screen.getByRole("button", { name: "Run synthetic trials" }));
  await act(() => vi.advanceTimersByTimeAsync(101));
  expect(screen.getByText(/No verified saved forecast matches an upcoming/)).toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "Synthetic simulation result" })).not.toBeInTheDocument();
});
