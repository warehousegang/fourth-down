import { render, screen, fireEvent } from "@testing-library/react";
import { expect, it } from "vitest";
import { completedFixture, operationsFixture } from "./intelligence-fixtures";
import { WeeklyIntelligence } from "./WeeklyIntelligence";

it("withholds intelligence when validated evidence is unavailable", () => {
  const {container}=render(<WeeklyIntelligence operations={null} week={7}/>);
  expect(container).toBeEmptyDOMElement();
});
it("does not manufacture an accuracy or surprise value before verified finals", () => {
  render(<WeeklyIntelligence operations={operationsFixture()} week={7}/>);
  expect(screen.getByRole("heading",{name:"Awaiting verified outcomes"})).toBeVisible();
  expect(screen.getByText("Partial week · 0 scored · 13 pending")).toBeVisible();
  expect(screen.queryByText("0.0%")).not.toBeInTheDocument();
});
it("makes assumptions, small samples, exclusions and original upset evidence inspectable", () => {
  const ops=completedFixture(24,17);
  const {container}=render(<WeeklyIntelligence operations={ops} week={7}/>);
  expect(screen.getByText(/calibration is uncertain/)).toBeVisible();
  const summary=screen.getByText("Explore the week’s outcomes & method"); fireEvent.click(summary);
  // Native details supplies keyboard semantics; browser tests exercise real activation.
  expect(container.querySelector("details > summary")).toBe(summary);
  expect(screen.getByText(/small sample cannot distinguish/)).toBeInTheDocument();
  expect(screen.getByText(/No historical percentile/)).toBeInTheDocument();
  expect(screen.getByText(/incomplete week/)).toBeInTheDocument();
  expect(container.querySelector(".weekly-upsets time")?.getAttribute("datetime")).toBe(ops.catalog.find(f=>f.selected_final)!.generated_at);
  expect(screen.getByRole("link",{name:/Saints won/})).toHaveAttribute("href",`#intelligence?game=${ops.games[0].id}`);
});
it("refreshes the analysis and removes a prior upset after a verified score correction", () => {
  const {rerender}=render(<WeeklyIntelligence operations={completedFixture(24,17)} week={7}/>);
  expect(screen.getByRole("heading",{name:"Picks trailed expectation"})).toBeVisible();
  rerender(<WeeklyIntelligence operations={completedFixture(17,24)} week={7}/>);
  expect(screen.getByRole("heading",{name:"Picks exceeded expectation"})).toBeVisible();
  expect(screen.queryByRole("link",{name:/Saints won/})).not.toBeInTheDocument();
});
