import { act, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useForecastClock } from "./use-forecast-clock";
function Probe({deadline}:{deadline:string}){const now=useForecastClock([deadline]);return <p>{now>=Date.parse(deadline)?"Expired":"Fresh"}</p>;}
afterEach(()=>vi.useRealTimers());
it("invalidates an open forecast at the exact deadline instead of waiting for a poll",()=>{
  vi.useFakeTimers();vi.setSystemTime(new Date("2026-10-24T12:00:00Z"));render(<Probe deadline="2026-10-24T12:00:01Z"/>);expect(screen.getByText("Fresh")).toBeInTheDocument();act(()=>vi.advanceTimersByTime(999));expect(screen.getByText("Fresh")).toBeInTheDocument();act(()=>vi.advanceTimersByTime(1));expect(screen.getByText("Expired")).toBeInTheDocument();
});
it("rechecks when a suspended tab resumes after expiry",()=>{
  vi.useFakeTimers();vi.setSystemTime(new Date("2026-10-24T12:00:00Z"));render(<Probe deadline="2026-10-24T12:10:00Z"/>);act(()=>{vi.setSystemTime(new Date("2026-10-24T13:00:00Z"));window.dispatchEvent(new Event("focus"));});expect(screen.getByText("Expired")).toBeInTheDocument();
});
it("does not reuse the initial loading clock when an artifact arrives after expiry",()=>{
  vi.useFakeTimers();vi.setSystemTime(new Date("2026-10-24T12:00:00Z"));const view=render(<Probe deadline="2026-10-24T12:01:00Z"/>);vi.setSystemTime(new Date("2026-10-24T12:02:00Z"));view.rerender(<Probe deadline="2026-10-24T12:01:00Z"/>);expect(screen.getByText("Expired")).toBeInTheDocument();
});
