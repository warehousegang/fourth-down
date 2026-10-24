import { render, screen } from "@testing-library/react";
import { beforeEach, afterEach, expect, it, vi } from "vitest";
import { CurrentContext } from "./CurrentContext";
import { loadContext } from "./context-contracts";
import { contextCapture, contextFixture } from "./intelligence-fixtures";
import { currentFixture } from "./current-fixture";
vi.mock("./context-contracts",async original=>({...await original<typeof import("./context-contracts")>(),loadContext:vi.fn()}));
beforeEach(()=>{vi.spyOn(Date,"now").mockReturnValue(Date.parse(contextFixture().generated_at));vi.mocked(loadContext).mockResolvedValue({data:contextFixture(),file:contextCapture.pointer.file,sha256:contextCapture.pointer.sha256});});
afterEach(()=>vi.restoreAllMocks());
it("shows sourced reports separately from probabilities and does not turn depth order into a starter",async()=>{
  render(<CurrentContext game={currentFixture().games[0]}/>);expect(await screen.findAllByText("Starter not confirmed.")).toHaveLength(2);expect(screen.getByText(/Injury report publication times are not supplied/)).toBeInTheDocument();expect(screen.getByText(/Original forecast cutoff/)).toBeInTheDocument();expect(screen.getAllByRole("region",{name:/descriptive team performance/})).toHaveLength(2);expect(screen.getByText(/They are not inputs to the frozen model/)).toBeInTheDocument();
});
it("withholds expired player reports instead of showing stale availability as current",async()=>{
  vi.spyOn(Date,"now").mockReturnValue(Date.parse(contextFixture().valid_until)+1);render(<CurrentContext game={currentFixture().games[0]}/>);expect(await screen.findByText(/Context snapshot expired/)).toBeInTheDocument();expect(screen.queryByText("Starter not confirmed.")).not.toBeInTheDocument();
});
it("requires context to match the current schedule version",async()=>{
  const game=currentFixture().games[0];game.kickoff="2026-10-27T00:00:00Z";render(<CurrentContext game={game}/>);expect(await screen.findByText(/No matching context snapshot/)).toBeInTheDocument();
});
it("handles a source failure independently without fabricated context",async()=>{
  vi.mocked(loadContext).mockRejectedValue(new Error("Current matchup context failed integrity validation."));render(<CurrentContext game={currentFixture().games[0]}/>);expect(await screen.findByText(/Current matchup context failed/)).toBeInTheDocument();expect(screen.queryByText("Starter not confirmed.")).not.toBeInTheDocument();
});
