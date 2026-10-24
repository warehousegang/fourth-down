import {
  render,
  screen,
  fireEvent,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { loadArtifact, artifactSchema } from "./contracts";
import demo from "../public/data/demo.json";
vi.mock("./contracts", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./contracts")>()),
  loadArtifact: vi.fn(),
}));
beforeEach(() => {
  window.location.hash = "matchups";
  vi.mocked(loadArtifact).mockResolvedValue(artifactSchema.parse(demo));
});
afterEach(() => vi.clearAllMocks());
describe("research interface", () => {
  it("shows unavailable instead of a probability for an unscorable matchup", async () => {
    const altered = artifactSchema.parse(demo);
    altered.games = altered.games.filter((g) => g.id === "2023_10_DET_LAC");
    Object.assign(altered.games[0], {
      status: "unavailable",
      reason: "Required feature missing",
      home_probability: null,
      factors: [],
    });
    vi.mocked(loadArtifact).mockResolvedValue(altered);
    render(<App />);
    const region = await screen.findByRole("region", {
      name: "Lions at Chargers forecast",
    });
    expect(
      within(region).getByText("Prediction unavailable"),
    ).toBeInTheDocument();
    expect(within(region).queryByText(/favored/)).not.toBeInTheDocument();
  });
  it("shows historical status and actual forecasts", async () => {
    render(<App />);
    expect(
      await screen.findByRole("heading", { name: /Game on/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Historical research, not live predictions/),
    ).toBeInTheDocument();
    expect(screen.getByText("58.8%")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Select week" })).toHaveValue(
      "4",
    );
  });
  it("changes the week and selects an actual matchup", async () => {
    render(<App />);
    fireEvent.change(
      await screen.findByRole("combobox", { name: "Select week" }),
      { target: { value: "1" } },
    );
    await waitFor(() => expect(window.location.hash).toContain("2023_01"));
    await waitFor(() => expect(screen.getByRole("combobox")).toHaveValue("1"));
  });
  it("shows failure instead of fabricated forecasts", async () => {
    vi.mocked(loadArtifact).mockRejectedValue(
      new Error("Invalid source artifact"),
    );
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Forecasts unavailable",
    );
    expect(screen.queryByText("58.8%")).not.toBeInTheDocument();
  });
  it("handles empty datasets", async () => {
    const empty = artifactSchema.parse(demo);
    empty.games = [];
    vi.mocked(loadArtifact).mockResolvedValue(empty);
    render(<App />);
    expect(
      await screen.findByText("No matchups available"),
    ).toBeInTheDocument();
  });
});
