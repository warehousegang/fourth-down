import { render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { App } from "./App";
import { readFileSync } from "node:fs";
import { loadOperations } from "./operations-contracts";
import { operationsFixture, operationsCapture, completedFixture } from "./intelligence-fixtures";
import { currentSchema, loadCurrent } from "./current-contracts";
const record = operationsFixture().catalog.filter(f => f.eligible).at(-1)!;
const currentPointer = {file:record.artifact_file,sha256:record.artifact_sha256};
const currentFixture = () => currentSchema.parse(JSON.parse(readFileSync(`public/data/current/${record.artifact_file}`,"utf8")));
vi.mock("./current-contracts", async original => ({...await original<typeof import("./current-contracts")>(), loadCurrent:vi.fn()}));
vi.mock("./operations-contracts", async original => ({...await original<typeof import("./operations-contracts")>(), loadOperations:vi.fn()}));
beforeEach(() => {
  vi.mocked(loadOperations).mockResolvedValue({data:operationsFixture(),file:operationsCapture.pointer.file,sha256:operationsCapture.pointer.sha256});
  window.location.hash = "current";
  const data = currentFixture();
  vi.spyOn(Date,"now").mockReturnValue(Date.parse(data.generated_at)+1000);
  vi.mocked(loadCurrent).mockResolvedValue({data,file:currentPointer.file,sha256:currentPointer.sha256});
});
afterEach(() => vi.restoreAllMocks());
it("shows current forecasts with limitations and no historical metric presented as current accuracy", async () => {
  render(<App/>);
  expect(await screen.findByRole("heading",{name:"Current Week Forecasts"})).toBeInTheDocument();
  expect(screen.getByText(/No injury, player-news, weather or prior-season strength adjustment/)).toBeInTheDocument();
  expect(screen.queryByText("58.8%")).not.toBeInTheDocument();
  expect(screen.getAllByText("MODEL ESTIMATE · NOT A GUARANTEE").length).toBeGreaterThan(0);
});
it("shows independent current error while preserving historical navigation", async () => {
  vi.mocked(loadCurrent).mockRejectedValue(new Error("No current forecast artifact is available."));
  render(<App/>);
  expect(await screen.findByRole("alert")).toHaveTextContent("Current forecasts unavailable");
  expect(screen.getByRole("link",{name:"2023 Matchups"})).toHaveAttribute("href", "#matchups");
});
it("labels verified expired forecasts as older without changing their probabilities", async () => {
  vi.spyOn(Date,"now").mockReturnValue(Date.parse(currentFixture().valid_until)+1);
  render(<App/>);
  expect(await screen.findByText("Older forecasts — not fresh")).toBeInTheDocument();
  expect(await screen.findAllByText("Older forecast",{exact:true})).toHaveLength(13);
  const counts=document.querySelector(".current-status-counts")!;
  expect([...counts.querySelectorAll("dt")].map(n=>n.textContent)).toEqual(["Displayable","Fresh","Older"]);
  expect([...counts.querySelectorAll("dd")].map(n=>n.textContent)).toEqual(["13 of 13","0","13"]);
  expect(screen.getAllByRole("link",{name:"View prediction data (JSON)"})).toHaveLength(13);
  const card=screen.getAllByRole("article")[0];
  const actions=within(card).getAllByRole("link");
  expect(actions.map(a=>a.textContent)).toEqual(["Explore matchup intelligence ","View prediction data (JSON)"]);
  expect(actions[0]).toHaveAttribute("href",`#intelligence?game=${encodeURIComponent(currentFixture().games[0].id)}`);
  expect(actions[1]).toHaveAttribute("href",`${import.meta.env.BASE_URL}data/current/${record.artifact_file}`);
  expect(card.querySelector(".current-cutoff time")).toHaveAttribute("datetime",currentFixture().games[0].generated_at);
  expect(within(card).getByText("Older forecast").closest("details")).not.toHaveAttribute("open");
  expect(screen.queryByText("MODEL ESTIMATE · NOT A GUARANTEE")).not.toBeInTheDocument();
});

it("shows a missing-result reason without a fabricated probability", async () => {
  const data = currentFixture();
  const g = data.games[0];
  Object.assign(g, {status:"unavailable",reason:"Final result not confirmed before cutoff",home_probability:null,away_probability:null,features:{},factors:[],history:{home:[],away:[]}});
  data.games = [g];
  vi.mocked(loadCurrent).mockResolvedValue({data,file:currentPointer.file,sha256:currentPointer.sha256});
  render(<App/>);
  expect(await screen.findByText("Final result not confirmed before cutoff")).toBeInTheDocument();
  expect(screen.queryByText("MODEL ESTIMATE · NOT A GUARANTEE")).not.toBeInTheDocument();
});

it("retains an eligible original after a stale-source attempt issues no new probability",async()=>{
  const data=currentFixture();const generated=new Date(Date.parse(data.valid_until)+60000).toISOString();
  data.generated_at=generated;
  for(const g of data.games)Object.assign(g,{status:"unavailable",reason:"Source is over 48 hours old; refresh before using forecasts",generated_at:generated,home_probability:null,away_probability:null,features:{},factors:[],history:{home:[],away:[]}});
  vi.spyOn(Date,"now").mockReturnValue(Date.parse(generated)+1000);
  vi.mocked(loadCurrent).mockResolvedValue({data,...currentPointer});
  render(<App/>);
  expect(await screen.findAllByText("Older forecast",{exact:true})).toHaveLength(13);
  expect(screen.getAllByText(/No late-breaking injuries, weather or news are included/)).toHaveLength(1);
  for (const [index,card] of screen.getAllByRole("article").entries()) {
    expect(card.querySelector(".current-cutoff time")).toHaveAttribute("datetime",currentFixture().games[index].generated_at);
  }
});
it("fails closed when archive provenance cannot be loaded",async()=>{
  vi.mocked(loadOperations).mockRejectedValue(new Error("History checksum mismatch"));
  render(<App/>);
  expect(await screen.findByText(/Forecast provenance unavailable/)).toBeInTheDocument();
  expect(document.querySelectorAll(".current-probabilities")).toHaveLength(0);
});


it.each([[24,17,"Saints"],[17,24,"Steelers"],[24,24,null]] as const)("retains the archived card after refresh and shows verified final %i–%i",async(home,away,winner)=>{
  const ops=completedFixture(home,away);
  const game=ops.games[0];
  const selected=ops.catalog.find(f=>f.id===game.final_forecast_id)!;
  const current=currentFixture(); current.games=[]; current.week=8;
  current.generated_at=ops.generated_at;
  vi.spyOn(Date,"now").mockReturnValue(Date.parse(ops.generated_at)+1);
  vi.mocked(loadCurrent).mockResolvedValue({data:current,...currentPointer});
  vi.mocked(loadOperations).mockResolvedValue({data:ops,...operationsCapture.pointer});
  render(<App/>);
  const card=await screen.findByRole("article",{name:"Steelers at Saints current forecast"});
  expect(within(card).getByText("Archived pregame prediction")).toBeInTheDocument();
  expect(card).toHaveTextContent(`Verified final: PIT ${away} · NO ${home}`);
  expect(card).toHaveTextContent(winner?`Actual winner: ${winner}`:"Tie excluded from binary scoring.");
  expect(card.querySelector(".current-cutoff time")).toHaveAttribute("datetime",selected.generated_at);
  expect([...card.querySelectorAll(".current-probabilities strong")].map(n=>n.textContent)).toEqual([`${(selected.away_probability!*100).toFixed(1)}%`,`${(selected.home_probability!*100).toFixed(1)}%`]);
  if(winner)expect(card).toHaveTextContent(`Brier: ${game.evaluations.find(e=>e.primary)!.brier.toFixed(4)}`);
  else expect(card).not.toHaveTextContent("Brier:");
});

it("keeps pregame percentages at kickoff without inferring a live status or result",async()=>{
  const data=currentFixture(); const first=data.games[0];
  vi.spyOn(Date,"now").mockReturnValue(Date.parse(first.kickoff!));
  render(<App/>);
  const card=await screen.findByRole("article",{name:"Steelers at Saints current forecast"});
  expect(await within(card).findByText("Archived pregame prediction")).toBeInTheDocument();
  expect(card).toHaveTextContent("awaiting verified game status and final result");
  expect(card).not.toHaveTextContent("Verified final:");
  expect(card).not.toHaveTextContent("Brier:");
});

it("retains archived intelligence deep links when refresh has removed the upcoming game",async()=>{
  const ops=completedFixture(); const current=currentFixture(); current.games=[];
  current.generated_at=ops.generated_at;
  vi.spyOn(Date,"now").mockReturnValue(Date.parse(ops.generated_at)+1);
  vi.mocked(loadCurrent).mockResolvedValue({data:current,...currentPointer});
  vi.mocked(loadOperations).mockResolvedValue({data:ops,...operationsCapture.pointer});
  window.location.hash=`intelligence?game=${ops.games[0].id}`;
  render(<App/>);
  expect(await screen.findByText("Archived pregame prediction")).toBeInTheDocument();
  expect(screen.getByText(/Actual winner: Saints/)).toBeInTheDocument();
  expect(screen.getByRole("region",{name:"Current matchup model factors"}).querySelectorAll("tbody tr")).toHaveLength(4);
});
