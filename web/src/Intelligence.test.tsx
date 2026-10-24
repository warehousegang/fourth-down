import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { App } from "./App";
import { loadOperations } from "./operations-contracts";
import { loadResearch } from "./research-contracts";
import { loadCurrent } from "./current-contracts";
import { loadContext } from "./context-contracts";
import { completedFixture, contextCapture, contextFixture, operationsCapture, operationsFixture, researchCapture, researchFixture } from "./intelligence-fixtures";
import { currentFixture, currentPointer } from "./current-fixture";
vi.mock("./operations-contracts",async original=>({...await original<typeof import("./operations-contracts")>(),loadOperations:vi.fn()}));
vi.mock("./research-contracts",async original=>({...await original<typeof import("./research-contracts")>(),loadResearch:vi.fn()}));
vi.mock("./current-contracts",async original=>({...await original<typeof import("./current-contracts")>(),loadCurrent:vi.fn()}));
vi.mock("./context-contracts",async original=>({...await original<typeof import("./context-contracts")>(),loadContext:vi.fn()}));
beforeEach(()=>{
  window.location.hash="history";
  vi.mocked(loadOperations).mockResolvedValue({data:operationsFixture(),file:operationsCapture.pointer.file,sha256:operationsCapture.pointer.sha256});
  vi.mocked(loadResearch).mockResolvedValue({data:researchFixture(),file:researchCapture.pointer.file,sha256:researchCapture.pointer.sha256});
  vi.mocked(loadCurrent).mockResolvedValue({data:currentFixture(),file:currentPointer.file,sha256:currentPointer.sha256});
  vi.mocked(loadContext).mockResolvedValue({data:contextFixture(),file:contextCapture.pointer.file,sha256:contextCapture.pointer.sha256});
  vi.spyOn(Date,"now").mockReturnValue(Math.max(Date.parse(currentFixture().generated_at),Date.parse(contextFixture().generated_at)));
});
afterEach(()=>vi.restoreAllMocks());
it("shows immutable originals, updated records and pending final designation",async()=>{
  render(<App/>);expect(await screen.findByRole("heading",{name:"Forecast History"})).toBeInTheDocument();expect(screen.getByText("Not designated before kickoff")).toBeInTheDocument();expect(screen.getByText("Original record")).toBeInTheDocument();expect(screen.getByText("Latest record")).toBeInTheDocument();expect(screen.getByText("0.00 pp")).toBeInTheDocument();
  fireEvent.click(screen.getAllByText(/Inputs and provenance/)[0]);expect(screen.getAllByRole("link",{name:"Download original forecast artifact"})[0]).toHaveAttribute("href",expect.stringContaining("data/current/forecast-2026-"));
});
it("shows zero prospective outcomes without copying historical accuracy",async()=>{
  window.location.hash="postgame";render(<App/>);expect(await screen.findByRole("heading",{name:"No completed forecasted games yet"})).toBeInTheDocument();expect(screen.getAllByText("Not established")).toHaveLength(3);expect(screen.queryByText("58.8%")).not.toBeInTheDocument();
});
it("renders synthetic completed facts separately from hypotheses and original forecasts",async()=>{
  window.location.hash="postgame";vi.mocked(loadOperations).mockResolvedValue({data:completedFixture(),file:operationsCapture.pointer.file,sha256:operationsCapture.pointer.sha256});render(<App/>);expect(await screen.findByRole("heading",{name:"Verified game facts"})).toBeInTheDocument();expect(screen.getByRole("heading",{name:"Hypotheses to investigate"})).toBeInTheDocument();expect(screen.getByText(/Synthetic test fixture/)).toBeInTheDocument();expect(screen.getByText(/Hypotheses are not verified causes/)).toBeInTheDocument();
});
it("matches all12 domains with frozen factors and honest player-data gaps",async()=>{
  window.location.hash="intelligence";render(<App/>);expect(await screen.findByRole("region",{name:"Current matchup model factors"})).toBeInTheDocument();await waitFor(()=>expect(document.querySelectorAll(".domain-card")).toHaveLength(12));expect(screen.getByText(/Game-time weather, verified team developments/)).toBeInTheDocument();expect(screen.getAllByText("NOT TRAINED · NOT USED").length).toBeGreaterThan(0);fireEvent.change(screen.getByRole("combobox",{name:"Compare teams"}),{target:{value:currentFixture().games[1].id}});await waitFor(()=>expect(window.location.hash).toContain(currentFixture().games[1].id));
});
it("keeps current evidence available when research loading fails",async()=>{
  window.location.hash="models";vi.mocked(loadResearch).mockRejectedValue(new Error("Research checksum mismatch"));render(<App/>);expect(await screen.findByText(/No scored prospective games yet/)).toBeInTheDocument();expect(await screen.findByRole("alert")).toHaveTextContent("Research checksum mismatch");expect(screen.getByRole("link",{name:/Open the separate 2023/})).toHaveAttribute("href","#performance");
});
it("keeps research evidence available when operations loading fails",async()=>{
  window.location.hash="models";vi.mocked(loadOperations).mockRejectedValue(new Error("Operations unavailable"));render(<App/>);expect(await screen.findByText("Research only. Not promoted.")).toBeInTheDocument();expect(screen.getByRole("alert")).toHaveTextContent("Operations unavailable");expect(within(screen.getByRole("region",{name:"Research chronological folds"})).getAllByRole("row")).toHaveLength(7);
});
it("shows observed completed status separately from current predictions",async()=>{
  window.location.hash="current";render(<App/>);const region=await screen.findByRole("region",{name:"Observed Week 7 schedule"});expect(within(region).getByText("completed")).toBeInTheDocument();expect(within(region).getAllByText("scheduled")).toHaveLength(13);fireEvent.change(screen.getByRole("combobox",{name:"Schedule week"}),{target:{value:"18"}});expect(await screen.findByRole("region",{name:"Observed Week 18 schedule"})).toBeInTheDocument();expect(screen.getAllByText("Unconfirmed").length).toBeGreaterThan(0);
});
