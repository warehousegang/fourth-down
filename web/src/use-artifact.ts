import { useEffect, useState } from "react";

export function useArtifact<T>(load: () => Promise<T>, intervalMs=0) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    let pending=false;
    const refresh=()=>{
      if(pending)return;
      pending=true;
      load().then(value=>{if(active){setData(value);setError("");}})
        .catch(e=>{if(active)setError(e instanceof Error?e.message:"Artifact unavailable");})
        .finally(()=>{pending=false;});
    };
    refresh();
    const timer=intervalMs?setInterval(()=>{if(document.visibilityState!=="hidden")refresh();},intervalMs):null;
    const resume=()=>{if(intervalMs&&document.visibilityState!=="hidden")refresh();};
    document.addEventListener("visibilitychange",resume);
    return () => { active = false; if(timer)clearInterval(timer);document.removeEventListener("visibilitychange",resume); };
  }, [load, attempt, intervalMs]);
  return { data, error, retry: () => setAttempt(value => value + 1) };
}
