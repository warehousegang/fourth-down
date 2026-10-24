import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { TeamMark } from "./TeamMark";
import { teams } from "./teams";

it("provides all 32 team logos with full team-name alternatives and local URLs", () => {
  expect(Object.keys(teams)).toHaveLength(32);
  render(<>{Object.keys(teams).map(code => <TeamMark key={code} code={code}/>)}</>);
  expect(screen.getAllByRole("img")).toHaveLength(32);
  for (const [code, identity] of Object.entries(teams)) {
    const logo = screen.getByRole("img", { name: `${identity.city} ${identity.name}` });
    expect(logo.tagName).toBe("IMG");
    expect(logo.getAttribute("src")).toContain(`${code.toLowerCase()}.png`);
    expect(logo.getAttribute("src")).toMatch(/^\/(?!\/)/);
    expect(logo).toHaveAttribute("loading", "lazy");
    expect(logo).toHaveAttribute("width", "156");
    expect(logo).toHaveAttribute("height", "156");
  }
});

it.each([['LAR','Los Angeles Rams'],['WSH','Washington Commanders'],['JAC','Jacksonville Jaguars'],['det','Detroit Lions']])(
  "resolves the %s display alias without changing forecast codes", (code, name) => {
    render(<TeamMark code={code}/>);
    expect(screen.getByRole("img", { name }).tagName).toBe("IMG");
  },
);

it("replaces a failed image with an accessible abbreviation and recovers on team selection", () => {
  const { rerender } = render(<TeamMark code="DET"/>);
  fireEvent.error(screen.getByRole("img", { name: "Detroit Lions" }));
  const fallback = screen.getByRole("img", { name: "Detroit Lions" });
  expect(fallback.tagName).toBe("SPAN");
  expect(fallback).toHaveTextContent("DET");
  rerender(<TeamMark code="GB"/>);
  expect(screen.getByRole("img", { name: "Green Bay Packers" }).tagName).toBe("IMG");
  rerender(<TeamMark code="DET"/>);
  expect(screen.getByRole("img", { name: "Detroit Lions" }).tagName).toBe("IMG");
});

it("uses a text fallback without requesting an image for an unknown team", () => {
  const { container } = render(<TeamMark code="UNKNOWN" size="current"/>);
  expect(container.querySelector("img")).toBeNull();
  expect(screen.getByRole("img", { name: "UNKNOWN" })).toHaveTextContent("UNKNOWN");
});
