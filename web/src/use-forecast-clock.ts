import { useEffect, useState } from "react";

/** Recheck at the exact expiry/kickoff boundary, with a periodic clock-change fallback. */
export function useForecastClock(deadlines: (string | null)[]) {
  const [now,setNow]=useState(Date.now());
  const key=deadlines.filter(Boolean).join("|");
  useEffect(()=>{
    const observed=Date.now();
    const remaining=key.split("|").map(t=>Date.parse(t)-observed).filter(t=>Number.isFinite(t)&&t>0);
    const wait=Math.max(1,Math.min(30000,...remaining));
    const timer=setTimeout(()=>setNow(Date.now()),wait);
    const resume=()=>setNow(Date.now());
    window.addEventListener("focus",resume);
    document.addEventListener("visibilitychange",resume);
    return()=>{clearTimeout(timer);window.removeEventListener("focus",resume);document.removeEventListener("visibilitychange",resume);};
  },[key,now]);
  return Math.max(now, Date.now());
}
