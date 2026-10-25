import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { App } from "./App";
import { readFileSync } from "node:fs";
import { loadOperations } from "./operations-contracts";
import { operationsFixture, operationsCapture } from "./intelligence-fixtures";
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
  expect(await screen.findByText(/Older forecast warning/)).toBeInTheDocument();
  expect(await screen.findAllByText("OLDER FORECAST · NOT FRESH")).toHaveLength(13);
  expect(screen.getByText("0 fresh · 13 older")).toBeInTheDocument();
  expect(screen.getAllByRole("link",{name:"Original forecast JSON"})).toHaveLength(13);
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
  expect(await screen.findAllByText("OLDER FORECAST · NOT FRESH")).toHaveLength(13);
  expect(screen.getAllByText(/Older forecast: generated/)).toHaveLength(13);
});
it("fails closed when archive provenance cannot be loaded",async()=>{
  vi.mocked(loadOperations).mockRejectedValue(new Error("History checksum mismatch"));
  render(<App/>);
  expect(await screen.findByText(/Forecast provenance unavailable/)).toBeInTheDocument();
  expect(document.querySelectorAll(".current-probabilities")).toHaveLength(0);
});
