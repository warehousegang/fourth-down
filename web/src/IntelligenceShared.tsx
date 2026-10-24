import type { ReactNode } from "react";
import { ArrowUpRight, RefreshCw } from "lucide-react";

export const pct = (value: number | null) => value === null ? "Not established" : `${(value * 100).toFixed(1)}%`;
export const decimal = (value: number | null) => value === null ? "Not established" : value.toFixed(4);
export const time = (value: string | null) => value ? new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit", timeZone: "America/New_York", timeZoneName: "short" }).format(new Date(value)) : "Unconfirmed";
export const signed = (value: number) => `${value > 0 ? "+" : ""}${value.toFixed(2)}`;
export function Heading({ label, title, children }: { label: string; title: string; children: ReactNode }) {
  return <section className="page-heading intelligence-heading"><div className="eyebrow">// {label}</div><h1>{title}</h1><p>{children}</p></section>;
}
export function LoadState({ title, error, retry }: { title: string; error: string; retry: () => void }) {
  return <section className="empty-state" role={error ? "alert" : "status"}><h1>{error ? `${title} unavailable` : `Loading ${title}`}</h1><p>{error || "Checking artifact integrity and evidence…"}</p>{error && <button onClick={retry}>Retry artifact load</button>}</section>;
}
export function Provenance({ label, directory, file, hash, generated, retry }: { label: string; directory: string; file: string; hash: string; generated: string; retry: () => void }) {
  return <footer className="intelligence-provenance"><span>{label} · Generated {time(generated)}</span><a href={`${import.meta.env.BASE_URL}data/${directory}/${file}`} download>Download verified artifact <ArrowUpRight size={13}/></a><details><summary>Artifact checksum</summary><p>{hash}</p></details><button className="current-reload" onClick={retry}><RefreshCw size={14}/> Reload local evidence</button></footer>;
}
export function Table({ label, children }: { label: string; children: ReactNode }) {
  return <div className="intelligence-table" role="region" aria-label={label} tabIndex={0}><table>{children}</table></div>;
}
export function Metrics({ value, label }: { value: { count: number; accuracy: number | null; brier: number | null; log_loss: number | null }; label: string }) {
  return <section className="intelligence-metrics" aria-label={label}>{[["Scored forecasts", String(value.count)], ["Accuracy", pct(value.accuracy)], ["Brier score", decimal(value.brier)], ["Log loss", decimal(value.log_loss)]].map(([name, result]) => <div className="panel" key={name}><span className="eyebrow">{name}</span><strong>{result}</strong></div>)}</section>;
}
