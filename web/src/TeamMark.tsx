import { useState } from "react";
import { team, teams } from "./teams";

// Vite emits fingerprinted, same-origin files under the configured base path.
// Importing URLs does not download images; the browser loads only rendered marks.
const images = import.meta.glob<string>("./assets/team-logos/*.png", {
  eager: true,
  import: "default",
  query: "?url&no-inline",
});
const aliases: Record<string, string> = { LAR: "LA", WSH: "WAS", JAC: "JAX" };

export function TeamMark({ code, size = "matchup" }: {
  code: string;
  size?: "matchup" | "current";
}) {
  const normalized = code.toUpperCase();
  const canonical = aliases[normalized] || normalized;
  const known = Object.hasOwn(teams, canonical);
  const identity = team(canonical);
  const label = known ? `${identity.city} ${identity.name}` : code;
  const src = known ? images[`./assets/team-logos/${canonical.toLowerCase()}.png`] : undefined;
  return <span className={`team-mark team-mark--${size}`}>
    <LogoOrIdentifier key={canonical} src={src} code={canonical} label={label}/>
  </span>;
}

function LogoOrIdentifier({ src, code, label }: {src?: string; code: string; label: string}) {
  const [failed, setFailed] = useState(false);
  return src && !failed
    ? <img className="team-logo" src={src} alt={label} width="156" height="156"
        loading="lazy" decoding="async" onError={() => setFailed(true)}/>
    : <span className="team-identifier" role="img" aria-label={label}>{code}</span>;
}
