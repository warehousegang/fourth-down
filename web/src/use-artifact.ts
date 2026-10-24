import { useEffect, useState } from "react";

export function useArtifact<T>(load: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setData(null); setError("");
    load().then(value => { if (active) setData(value); }).catch(e => { if (active) setError(e instanceof Error ? e.message : "Artifact unavailable"); });
    return () => { active = false; };
  }, [load, attempt]);
  return { data, error, retry: () => setAttempt(value => value + 1) };
}
