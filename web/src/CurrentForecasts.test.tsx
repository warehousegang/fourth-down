import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { App } from "./App";
import { loadCurrent } from "./current-contracts";
import { currentFixture, currentPointer } from "./current-fixture";
vi.mock("./current-contracts", async original => ({...await original<typeof import("./current-contracts")>(), loadCurrent:vi.fn()}));
beforeEach(() => {
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
it("hides probabilities when the snapshot is expired", async () => {
  vi.spyOn(Date,"now").mockReturnValue(Date.parse(currentFixture().valid_until)+1);
  render(<App/>);
  expect(await screen.findByText(/Snapshot expired — probabilities hidden/)).toBeInTheDocument();
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
