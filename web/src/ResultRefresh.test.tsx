import { act, cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ObservedSchedule } from "./ObservedSchedule";
import { PostgameAnalysis } from "./PostgameAnalysis";
import { ForecastHistory } from "./ForecastHistory";
import { ModelIntelligence } from "./ModelIntelligence";
import { loadOperations } from "./operations-contracts";
import { loadResearch } from "./research-contracts";
import { completedFixture, operationsCapture, operationsFixture, researchCapture, researchFixture } from "./intelligence-fixtures";

vi.mock("./operations-contracts", async original => ({...await original<typeof import("./operations-contracts")>(), loadOperations:vi.fn()}));
vi.mock("./research-contracts", async original => ({...await original<typeof import("./research-contracts")>(), loadResearch:vi.fn()}));
const wrap = (data:ReturnType<typeof operationsFixture>) => ({data,...operationsCapture.pointer});
beforeEach(() => {
  vi.useFakeTimers();
  vi.spyOn(document,"visibilityState","get").mockReturnValue("visible");
  vi.mocked(loadOperations).mockResolvedValue(wrap(operationsFixture()));
  vi.mocked(loadResearch).mockResolvedValue({data:researchFixture(),...researchCapture.pointer});
});
afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks(); });

it.each(["schedule","postgame","history","models"])("refreshes the open %s view after a final is published", async view => {
  const pending=operationsFixture(), complete=completedFixture(), game=complete.games[0];
  render(view==="schedule" ? <ObservedSchedule initialWeek={game.week}/> : view==="postgame" ? <PostgameAnalysis/> : view==="history" ? <ForecastHistory/> : <ModelIntelligence/>);
  await act(async()=>{});
  const original=pending.catalog.find(f=>f.id===pending.games[0].original_forecast_id)!;
  if(view==="schedule") expect(screen.getByRole("row",{name:new RegExp(`${game.away} at ${game.home}`)})).toHaveTextContent("scheduled");
  if(view==="postgame") expect(screen.getByRole("heading",{name:"No completed forecasted games yet"})).toBeInTheDocument();
  if(view==="history") expect(screen.getByText("Not designated before kickoff")).toBeInTheDocument();
  if(view==="models") expect(screen.getByText(/No scored prospective games yet/)).toBeInTheDocument();
  vi.mocked(loadOperations).mockResolvedValue(wrap(complete));
  await act(async()=>{ await vi.advanceTimersByTimeAsync(60_000); });
  const expectCompleted=()=>{
    if(view==="schedule") expect(screen.getByRole("row",{name:new RegExp(`${game.away} at ${game.home}`)})).toHaveTextContent("completed");
    if(view==="postgame") expect(screen.getByRole("heading",{name:`${game.away} 17 at ${game.home} 24`})).toBeInTheDocument();
    if(view==="history") {
      expect(screen.queryByText("Not designated before kickoff")).not.toBeInTheDocument();
      expect(screen.getByText("FINAL PREGAME")).toBeInTheDocument();
      expect(screen.getAllByText(`${original.home} ${(original.home_probability!*100).toFixed(1)}%`).length).toBeGreaterThan(0);
    }
    if(view==="models") expect(within(screen.getByRole("region",{name:"Current incumbent metrics"})).getByText("1")).toBeInTheDocument();
  };
  expectCompleted();
  vi.mocked(loadOperations).mockRejectedValueOnce(new Error("offline"));
  await act(async()=>{ await vi.advanceTimersByTimeAsync(60_000); });
  expectCompleted();
  expect(screen.getByRole("status")).toHaveTextContent("Showing the last verified data");
});

it("keeps verified finals during a polling outage and accepts the next corrected score", async()=>{
  const first=completedFixture(), corrected=completedFixture(17,24), game=first.games[0];
  vi.mocked(loadOperations).mockResolvedValueOnce(wrap(first)).mockRejectedValueOnce(new Error("offline")).mockResolvedValue(wrap(corrected));
  render(<PostgameAnalysis/>); await act(async()=>{});
  const originalHeading=`${game.away} 17 at ${game.home} 24`;
  expect(screen.getByRole("heading",{name:originalHeading})).toBeInTheDocument();
  await act(async()=>{ await vi.advanceTimersByTimeAsync(60_000); });
  expect(screen.getByRole("heading",{name:originalHeading})).toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("Showing the last verified data");
  await act(async()=>{ await vi.advanceTimersByTimeAsync(60_000); });
  expect(screen.queryByRole("heading",{name:originalHeading})).not.toBeInTheDocument();
  expect(screen.getByRole("heading",{name:`${game.away} 24 at ${game.home} 17`})).toBeInTheDocument();
  expect(screen.queryByText(/Showing the last verified data/)).not.toBeInTheDocument();
});
