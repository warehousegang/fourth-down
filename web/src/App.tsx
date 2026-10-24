import { useEffect, useState } from "react";
import {
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  BarChart3,
  Check,
  Clock3,
  ChevronRight,
  CircleHelp,
  Database,
  FlaskConical,
  GitBranch,
  Layers3,
  History,
  ClipboardCheck,
  LockKeyhole,
  MapPin,
  ShieldCheck,
  Sparkles,
  Target,
  Trophy,
} from "lucide-react";
import { loadArtifact, type Artifact, type Game } from "./contracts";
import { team } from "./teams";
import exposure from "../../docs/HOLDOUT_EXPOSURE.json";
import { CurrentForecasts } from "./CurrentForecasts";
import { ForecastHistory } from "./ForecastHistory";
import { PostgameAnalysis } from "./PostgameAnalysis";
import { MatchupIntelligence } from "./MatchupIntelligence";
import { ModelIntelligence } from "./ModelIntelligence";

const routes = [
  "current",
  "intelligence",
  "history",
  "postgame",
  "models",
  "matchups",
  "explanation",
  "performance",
  "architecture",
] as const;
type Route = (typeof routes)[number];
const nav = [
  ["current", "Current Week Forecasts", Clock3, "Upcoming Games"],
  ["intelligence", "Matchup Intelligence", Target, "Matchup Intelligence"],
  ["history", "Forecast History", History, "Forecast History"],
  ["models", "Model Intelligence", BarChart3, "Model Intelligence"],
  ["postgame", "Postgame Analysis", ClipboardCheck, "Postgame Analysis"],
  ["architecture", "Architecture", Layers3, "Engineering"],
] as const;
const historicalNav = [
  ["matchups", "2023 Matchups", Trophy],
  ["explanation", "Prediction explanation", Target],
  ["performance", "Model performance", BarChart3],
] as const;
const needsHistorical = (route: Route) => ["matchups", "explanation", "performance", "architecture"].includes(route);
function locationState() {
  const [path, query = ""] = window.location.hash.slice(1).split("?");
  return {
    route: (routes.includes(path as Route) ? path : "current") as Route,
    game: new URLSearchParams(query).get("game"),
  };
}
const pct = (p: number) => `${(p * 100).toFixed(1)}%`;
const signed = (v: number, digits = 2) =>
  `${v > 0 ? "+" : ""}${v.toFixed(digits)}`;
const date = (value: string) =>
  new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "America/New_York",
  }).format(new Date(value));
const kickoff = (value: string | null) =>
  value
    ? new Intl.DateTimeFormat("en-US", {
        weekday: "short",
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
        timeZone: "America/New_York",
        timeZoneName: "short",
      }).format(new Date(value))
    : "Kickoff unavailable";

export function App() {
  const [data, setData] = useState<Artifact | null>(null);
  const [error, setError] = useState("");
  const [location, setLocation] = useState(locationState);
  const [week, setWeek] = useState(4);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!needsHistorical(location.route)) return;
    let active = true;
    setError("");
    loadArtifact()
      .then((d) => {
        if (active) setData(d);
      })
      .catch((e) => {
        if (active)
          setError(e instanceof Error ? e.message : "Forecasts unavailable.");
      });
    return () => {
      active = false;
    };
  }, [attempt, needsHistorical(location.route)]);
  useEffect(() => {
    const handler = () => setLocation(locationState());
    window.addEventListener("hashchange", handler);
    return () => window.removeEventListener("hashchange", handler);
  }, []);
  const selected =
    data?.games.find((g) => g.id === location.game) ||
    data?.games.find(
      (g) => g.week === week && (g.home === "DET" || g.away === "DET"),
    ) ||
    data?.games.find((g) => g.week === week) ||
    data?.games[0];
  const visibleWeek = selected?.week ?? week;
  const go = (route: Route, game?: string) => {
    window.location.hash = `${route}${game ? `?game=${encodeURIComponent(game)}` : ""}`;
  };
  const changeWeek = (value: number) => {
    setWeek(value);
    const first = data?.games.find((g) => g.week === value);
    go(location.route, first?.id);
  };
  const current = data?.evaluation.models.find(
    (m) => m.id === data.evaluation.selected,
  );
  return (
    <div className="app-shell">
      <a
        className="skip-link"
        href="#main-content"
        onClick={(e) => {
          e.preventDefault();
          document.getElementById("main-content")?.focus();
        }}
      >
        Skip to content
      </a>
      <header className="site-header">
        <a className="brand" href="#current" aria-label="Fourth Down home">
          <span className="brand-mark">
            4<span>↗</span>
          </span>
          <span>
            FOURTH
            <span className="brand-down">
              DOWN<span className="brand-dot">.</span>
            </span>
          </span>
        </a>

        <nav aria-label="Main navigation">
          {nav.map(([id, label, Icon, display]) => (
            <a
              key={id}
              aria-label={label}
              className={location.route === id ? "nav-item active" : "nav-item"}
              href={`#${id}`}
              aria-current={location.route === id ? "page" : undefined}
            >
              <Icon size={18} />
              <span>{display}</span>
              {location.route === id && <span className="nav-dot" />}
            </a>
          ))}
        </nav>
      </header>
      <nav className="historical-nav" aria-label="Historical research navigation"><span>2023 RESEARCH</span>{historicalNav.map(([id,label,Icon])=><a key={id} aria-label={label} aria-current={location.route===id ? "page" : undefined} href={`#${id}${selected ? `?game=${selected.id}` : ""}`}><Icon size={13}/>{label}</a>)}</nav>
      <div className="main-shell">
        <header className="topbar">
          <span>
            WORKSPACE <ChevronRight size={13} />{" "}
            <strong>{[...nav, ...historicalNav].find((n) => n[0] === location.route)?.[1]}</strong>
          </span>
          <span className="replay-badge">
            <span /> {location.route === "current" || location.route === "intelligence" ? "UPCOMING · STATIC FORECAST" : needsHistorical(location.route) && location.route !== "architecture" ? "2023 HISTORICAL REPLAY" : "LOCAL EVIDENCE · REVIEW BUILD"}
          </span>
        </header>
        <main id="main-content" tabIndex={-1}>
          {location.route === "current" ? <CurrentForecasts /> : location.route === "history" ? <ForecastHistory/> : location.route === "postgame" ? <PostgameAnalysis/> : location.route === "intelligence" ? <MatchupIntelligence selectedId={location.game}/> : location.route === "models" ? <ModelIntelligence/> : error ? (
            <section className="empty-state" role="alert">
              <CircleHelp size={36} />
              <h1>Forecasts unavailable</h1>
              <p>{error}</p>
              <button onClick={() => setAttempt((a) => a + 1)}>
                Try again
              </button>
            </section>
          ) : !data ? (
            <section className="empty-state" role="status">
              <div className="loading-mark" />
              <h1>Loading the research desk</h1>
              <p>Checking model and forecast lineage…</p>
            </section>
          ) : (
            <>
              {location.route === "matchups" && (
                <>
                  <section className="page-heading hero-heading">
                    <div>
                      <div className="eyebrow">// NFL forecast lab</div>
                      <h1>
                        <span className="hero-intro">Game on.</span>
                        <span>Let the model call it.</span>
                      </h1>
                      <p>
                        Real matchups. Pregame probabilities.
                        <br />A scorecard that keeps the model honest.
                      </p>
                    </div>
                    <div className="season-control">
                      <span>SEASON</span>
                      <strong>
                        2023 <LockKeyhole size={13} />
                      </strong>
                    </div>
                  </section>
                  <div className="section-heading">
                    <div>
                      <h2>Explore the matchups</h2>
                      <span>
                        Pregame perspective. Transparent probabilities.
                      </span>
                    </div>
                    <label className="week-select">
                      Week{" "}
                      <select
                        aria-label="Select week"
                        value={visibleWeek}
                        onChange={(e) => changeWeek(Number(e.target.value))}
                      >
                        {[...new Set(data.games.map((g) => g.week))]
                          .sort((a, b) => a - b)
                          .map((w) => (
                            <option key={w} value={w}>
                              {String(w).padStart(2, "0")}
                            </option>
                          ))}
                      </select>
                    </label>
                  </div>
                  {selected ? (
                    <div className="matchup-layout">
                      <div className="selected-column">
                        <Matchup game={selected} data={data} />
                        <div className="metric-strip">
                          <Stat
                            label="VALIDATION GAMES"
                            value={data.evaluation.validation_n.toLocaleString()}
                            detail="2023 regular season"
                          />
                          <Stat
                            label="MODEL ACCURACY"
                            value={pct(current!.accuracy)}
                            detail="On the validation set"
                          />
                          <Stat
                            label="BRIER SCORE"
                            value={current!.brier.toFixed(4)}
                            detail="Lower is better"
                          />
                          <Stat
                            label="FINAL HOLDOUT"
                            value="Locked"
                            detail="Partially exposed · candidate locked"
                            locked
                          />
                        </div>
                        <div
                          className="game-list"
                          aria-label="Matchup selection"
                        >
                          <div className="list-heading">
                            WEEK {visibleWeek}{" "}
                            <span>
                              {
                                data.games.filter((g) => g.week === visibleWeek)
                                  .length
                              }{" "}
                              GAMES
                            </span>
                          </div>
                          {data.games
                            .filter((g) => g.week === visibleWeek)
                            .map((g) => (
                              <button
                                className={`game-button ${g.id === selected.id ? "selected" : ""}`}
                                key={g.id}
                                onClick={() => go("matchups", g.id)}
                                aria-pressed={g.id === selected.id}
                              >
                                <span className="game-date">
                                  {kickoff(g.kickoff)
                                    .split(",")
                                    .slice(0, 2)
                                    .join(",")}
                                </span>
                                <span className="game-button-row">
                                  <span className="mini-team">{g.away}</span>
                                  <span className="at">at</span>
                                  <span className="mini-team home">
                                    {g.home}
                                  </span>
                                  <ChevronRight size={16} />
                                </span>
                                <span className="game-button-bottom">
                                  {g.status === "available" &&
                                  g.home_probability !== null
                                    ? `${g.home_probability >= 0.5 ? g.home : g.away} ${pct(Math.max(g.home_probability, 1 - g.home_probability))}`
                                    : "Unavailable"}
                                  <span>MODEL ESTIMATE</span>
                                </span>
                              </button>
                            ))}
                        </div>
                        <div className="replay-notice">
                          <FlaskConical size={16} />
                          <span>
                            <strong>
                              Historical research, not live predictions.
                            </strong>{" "}
                            Replayed from pregame information. Model trained
                            through 2022.
                          </span>
                          <a href="#architecture">
                            How it works <ArrowUpRight size={13} />
                          </a>
                        </div>
                        <FactorPreview
                          game={selected}
                          onExplore={() => go("explanation", selected.id)}
                        />
                        <div className="quiet-note">
                          <ShieldCheck size={17} />
                          <p>
                            Every probability comes from the fitted model.
                            Missing data is shown as unavailable. No news or
                            injury assumptions are added.
                          </p>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <section className="empty-state">
                      <h2>No matchups available</h2>
                      <p>
                        The artifact contains no games. Regenerate the
                        historical replay.
                      </p>
                    </section>
                  )}
                </>
              )}
              {location.route === "explanation" && (
                <>
                  <PageHeading
                    eyebrow="INSIDE THE PREDICTION"
                    title="A probability you can trace."
                    text="Follow the inputs, the model, and the limits of what it knows."
                  />
                  {selected ? (
                    <>
                      <div className="explanation-title">
                        <h2>
                          {team(selected.away).name} at{" "}
                          {team(selected.home).name}
                        </h2>
                        <a href={`#matchups?game=${selected.id}`}>
                          Change matchup <ArrowRight size={15} />
                        </a>
                      </div>
                      <Matchup game={selected} data={data} compact />
                      {selected.status === "available" && (
                        <>
                          <section className="panel">
                            <PanelTitle
                              label="01 / PREGAME INPUTS"
                              title="The comparison before kickoff"
                            />
                            <p className="muted">
                              Only completed games before{" "}
                              {date(selected.cutoff)}, 12:00 a.m. Eastern,
                              contribute to these features.
                            </p>
                            <div
                              className="table-scroll"
                              role="region"
                              aria-label="Scrollable data table"
                              tabIndex={0}
                            >
                              <table>
                                <thead>
                                  <tr>
                                    <th>Feature</th>
                                    <th>{selected.away} · away</th>
                                    <th>{selected.home} · home</th>
                                    <th>Home − away</th>
                                    <th>Log-odds contribution</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {selected.factors.map((f) => (
                                    <tr key={f.key}>
                                      <td>
                                        <strong>{f.label}</strong>
                                        <small>
                                          {f.key.includes("smooth")
                                            ? "Four-game prior at 50%"
                                            : f.key.includes("recent")
                                              ? "Last five games · two-game prior"
                                              : f.key.includes("margin")
                                                ? "Points per game · four-game prior"
                                                : f.key.includes("rest")
                                                  ? "Days, capped at 14"
                                                  : "Season to date"}
                                        </small>
                                      </td>
                                      <td>{formatFeature(f.key, f.away)}</td>
                                      <td>{formatFeature(f.key, f.home)}</td>
                                      <td>{signed(f.difference)}</td>
                                      <td
                                        className={
                                          f.contribution >= 0
                                            ? "positive"
                                            : "negative"
                                        }
                                      >
                                        {signed(f.contribution, 3)}
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          </section>
                          <section className="panel">
                            <PanelTitle
                              label="02 / MODEL MATH"
                              title="From football features to a probability"
                            />
                            <div className="formula">
                              <span>
                                Intercept{" "}
                                <b>{signed(data.model.intercept, 3)}</b>
                              </span>
                              <span>+</span>
                              <span>
                                Feature contributions{" "}
                                <b>
                                  {signed(
                                    selected.factors.reduce(
                                      (a, f) => a + f.contribution,
                                      0,
                                    ),
                                    3,
                                  )}
                                </b>
                              </span>
                              <span>→</span>
                              <span>
                                Logistic transform{" "}
                                <b>
                                  {pct(selected.home_probability!)}{" "}
                                  {selected.home}
                                </b>
                              </span>
                            </div>
                            <p className="muted">
                              p(home win) = 1 / (1 + exp(−z)), where z is the
                              intercept plus all feature contributions. Positive
                              contributions favor the designated home team;
                              negative contributions favor the away team. These
                              are model associations, not causal claims.
                            </p>
                          </section>
                        </>
                      )}
                      <section className="panel limitation-panel">
                        <PanelTitle
                          label="03 / WHAT THE MODEL DOESN’T KNOW"
                          title="Context matters. This is an estimate."
                        />
                        <ul>
                          {data.limitations.map((x) => (
                            <li key={x}>{x}</li>
                          ))}
                        </ul>
                        {Math.min(
                          selected.history_games.home,
                          selected.history_games.away,
                        ) < 3 && (
                          <p>
                            <strong>Limited early-season history.</strong>{" "}
                            Priors have a larger influence on this matchup.
                          </p>
                        )}
                      </section>
                    </>
                  ) : (
                    <p>No matchup is available to explain.</p>
                  )}
                </>
              )}
              {location.route === "performance" && <Performance data={data} />}
              {location.route === "architecture" && (
                <Architecture data={data} />
              )}
              <footer>
                <span>
                  FOURTH DOWN <span className="footer-dot">/</span> An applied
                  ML research project
                </span>
                <span>
                  Derived from{" "}
                  <a
                    href={data.attribution.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {data.attribution.name}
                  </a>{" "}
                  ·{" "}
                  <a
                    href={data.attribution.license_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {data.attribution.license}
                  </a>
                </span>
                <a href={`${import.meta.env.BASE_URL}THIRD_PARTY_NOTICES.txt`}>
                  Third-party notices
                </a>
                <p>
                  Educational research only. Not affiliated with the NFL. Not
                  betting advice. Features and predictions are derived
                  modifications of source data.
                </p>
              </footer>
            </>
          )}
        </main>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  detail,
  locked = false,
}: {
  label: string;
  value: string;
  detail: string;
  locked?: boolean;
}) {
  return (
    <div className="stat">
      <span>{label}</span>
      <strong>
        {locked && <LockKeyhole size={22} />} {value}
      </strong>
      <small>{detail}</small>
    </div>
  );
}
function PageHeading({
  eyebrow,
  title,
  text,
}: {
  eyebrow: string;
  title: string;
  text: string;
}) {
  return (
    <section className="page-heading">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{text}</p>
      </div>
    </section>
  );
}
function PanelTitle({ label, title }: { label: string; title: string }) {
  return (
    <div className="panel-title">
      <span className="eyebrow">{label}</span>
      <h2>{title}</h2>
    </div>
  );
}
function formatFeature(key: string, value: number) {
  return key.includes("win")
    ? pct(value)
    : `${value.toFixed(1)}${key === "rest_diff" ? " d" : " pts"}`;
}

function TeamMark({ code }: { code: string }) {
  return (
    <div className="team-mark" aria-hidden="true">
      <span className="team-identifier">{code}</span>
    </div>
  );
}

function Matchup({
  game: g,
  data,
  compact = false,
}: {
  game: Game;
  data: Artifact;
  compact?: boolean;
}) {
  const home = team(g.home),
    away = team(g.away);
  return (
    <section
      className={`matchup-card ${compact ? "compact" : ""}`}
      aria-label={`${away.name} at ${home.name} forecast`}
    >
      <div className="matchup-meta">
        <span>
          <span className="status-dot" /> Featured matchup
        </span>
        <span>2023 historical replay · Week {g.week}</span>
      </div>
      <div className="field-stage">
        <div className="yard-markers" aria-hidden="true">
          {[20, 30, 40, 50, 40, 30, 20].map((yard, index) => (
            <span key={index}>{yard}</span>
          ))}
        </div>
        <div className="teams-row">
          <div className="team-block away-team">
            <span className="team-city">{away.city}</span>
            <TeamMark code={g.away} />
            <h2>{away.name}</h2>
            <span className="team-role">{g.away} · AWAY</span>
          </div>
          <div className="versus">
            VS
            <span className="field-center" aria-hidden="true" />
          </div>
          <div className="team-block home-team">
            <span className="team-city">{home.city}</span>
            <TeamMark code={g.home} />
            <h2>{home.name}</h2>
            <span className="team-role">
              {g.home} · HOME{g.neutral_site ? " · NEUTRAL VENUE" : ""}
            </span>
          </div>
        </div>
        <div className="venue">
          <MapPin size={14} />
          {g.stadium}
          <span className="venue-divider">/</span>
          {kickoff(g.kickoff)}
        </div>
      </div>
      {g.status === "available" && g.home_probability !== null ? (
        <div className="probability-section">
          <div className="probability-label">
            <span>ESTIMATED WIN PROBABILITY</span>
            <span>CONDITIONAL ON NO TIE</span>
          </div>
          <div className="probability-numbers">
            <strong className="away-prob">{pct(1 - g.home_probability)}</strong>
            <span className="model-pick">
              <Sparkles size={13} />
              {g.home_probability >= 0.5 ? g.home : g.away} favored
            </span>
            <strong className="home-prob">{pct(g.home_probability)}</strong>
          </div>
          <div
            className="probability-bar"
            role="img"
            aria-label={`${g.away} ${pct(1 - g.home_probability)}, ${g.home} ${pct(g.home_probability)}`}
          >
            <span style={{ width: `${(1 - g.home_probability) * 100}%` }} />
            <span style={{ width: `${g.home_probability * 100}%` }} />
          </div>
          <div className="probability-team-labels">
            <span>{g.away}</span>
            <span>{g.home}</span>
          </div>
        </div>
      ) : (
        <div className="unavailable" role="status">
          <strong>Prediction unavailable</strong>
          <p>{g.reason}</p>
        </div>
      )}
      <div className="matchup-action">
        <div>
          <h3>Who gets the win?</h3>
          <p>A model estimate. Every contributing factor explained.</p>
        </div>
        <a className="primary-button" href={`#explanation?game=${g.id}`}>
          Explore prediction <ArrowUpRight size={17} />
        </a>
      </div>
      <div className="forecast-stamp">
        <span>
          <ShieldCheck size={13} />
          {data.model.id}
        </span>
        <span>Replay generated {date(data.generated_at)}</span>
      </div>
    </section>
  );
}

function FactorPreview({
  game,
  onExplore,
}: {
  game: Game;
  onExplore: () => void;
}) {
  const factors = [...game.factors].sort(
    (a, b) => Math.abs(b.contribution) - Math.abs(a.contribution),
  );
  return (
    <section className="panel factor-panel">
      <div className="factor-heading">
        <div>
          <span className="eyebrow">BEHIND THE ESTIMATE</span>
          <h2>What’s moving the prediction?</h2>
        </div>
        <Target size={22} />
      </div>
      {game.status === "unavailable" ? (
        <p>No factors are available for an unscored matchup.</p>
      ) : factors.length ? (
        factors.slice(0, 3).map((f) => (
          <div className="factor-row" key={f.key}>
            <span
              className={`factor-icon ${f.contribution >= 0 ? "positive-bg" : "negative-bg"}`}
            >
              {f.contribution >= 0 ? (
                <ArrowUpRight size={18} />
              ) : (
                <ArrowDown size={18} />
              )}
            </span>
            <div>
              <strong>{f.label}</strong>
              <small>
                {game.away} {formatFeature(f.key, f.away)} <span>vs</span>{" "}
                {game.home} {formatFeature(f.key, f.home)}
              </small>
            </div>
            <span className="factor-contribution">
              {signed(f.contribution, 3)}
              <small>log-odds</small>
            </span>
          </div>
        ))
      ) : (
        <p>This constant baseline has no matchup-specific factors.</p>
      )}
      <button className="text-button" onClick={onExplore}>
        Explore the full explanation <ArrowRight size={16} />
      </button>
    </section>
  );
}

function Performance({ data: d }: { data: Artifact }) {
  const e = d.evaluation,
    current = e.models.find((m) => m.id === e.selected)!,
    baseline = e.models.find((m) => m.id === "home")!;
  return (
    <>
      <PageHeading
        eyebrow="MEASURED, NOT ASSUMED"
        title="Put the model to the test."
        text="Every comparison uses the same 272 non-tied games from the 2023 validation season."
      />
      <div className="metric-strip">
        <Stat
          label="VALIDATION ACCURACY"
          value={pct(current.accuracy)}
          detail={`${e.validation_n} games · fixed 50% threshold`}
        />
        <Stat
          label="BRIER SCORE"
          value={current.brier.toFixed(4)}
          detail={`${signed(current.brier - baseline.brier, 4)} vs home baseline`}
        />
        <Stat
          label="LOG LOSS"
          value={current.log_loss.toFixed(4)}
          detail="Lower is better"
        />
        <Stat
          label="TRAINING SAMPLE"
          value={e.train_n.toLocaleString()}
          detail="2010–2022 · non-tied games"
        />
      </div>
      <section className="panel">
        <PanelTitle
          label="01 / THE BENCHMARKS"
          title="A model has to earn its complexity."
        />
        <div
          className="table-scroll"
          role="region"
          aria-label="Scrollable data table"
          tabIndex={0}
        >
          <table>
            <thead>
              <tr>
                <th>Model</th>
                <th>Accuracy ↑</th>
                <th>Brier ↓</th>
                <th>Log loss ↓</th>
                <th>Games</th>
              </tr>
            </thead>
            <tbody>
              {e.models.map((m) => (
                <tr
                  key={m.id}
                  className={m.id === e.selected ? "selected-model" : ""}
                >
                  <td>
                    <strong>{m.name}</strong>
                    {m.id === e.selected && (
                      <span className="tag">SELECTED</span>
                    )}
                  </td>
                  <td>{pct(m.accuracy)}</td>
                  <td>{m.brier.toFixed(4)}</td>
                  <td>{m.log_loss.toFixed(4)}</td>
                  <td>{m.n}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted">
          {e.selection_rule} A 50/50 probability uses the same ≥50%
          classification rule and therefore always selects the home team.
        </p>
      </section>
      <div className="two-column">
        <section className="panel">
          <PanelTitle
            label="02 / CALIBRATION"
            title="Do the probabilities line up?"
          />
          <Calibration data={d} />
          <p className="muted">
            Home-win probability vs. observed home-win rate in fixed 10% bins.
            Circle size reflects sample count. The diagonal is perfect
            calibration.
          </p>
          <details>
            <summary>View calibration counts</summary>
            <table>
              <thead>
                <tr>
                  <th>Mean estimate</th>
                  <th>Observed</th>
                  <th>Games</th>
                </tr>
              </thead>
              <tbody>
                {e.calibration.map((b) => (
                  <tr key={b.bin}>
                    <td>{pct(b.predicted)}</td>
                    <td>{pct(b.observed)}</td>
                    <td>{b.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </section>
        <section className="panel evidence-card">
          <span className="eyebrow">THE HONEST READ</span>
          <h2>
            A useful signal.
            <br />
            More evidence needed.
          </h2>
          <div className="interval-value">
            {signed(e.brier_difference.mean, 4)}
          </div>
          <p>
            Mean Brier difference vs. the historical home baseline. Negative
            favors the model.
          </p>
          <div className="interval-box">
            <span>95% WEEK-RESAMPLED INTERVAL</span>
            <strong>
              {signed(e.brier_difference.low, 4)} <ArrowRight size={16} />{" "}
              {signed(e.brier_difference.high, 4)}
            </strong>
          </div>
          <p>
            {e.brier_difference.low <= 0 && e.brier_difference.high >= 0
              ? "The interval includes zero. This season does not establish a reliable improvement."
              : "This descriptive interval excludes zero, but validation selection limits inference."}{" "}
            Week-level resampling,{" "}
            {e.brier_difference.replicates.toLocaleString()} replicates, seed
            42.
          </p>
          <div className="holdout-callout">
            <LockKeyhole size={20} />
            <span>
              <strong>2024–2025 is partially exposed. Candidate evaluation locked.</strong>
              <small>
                The original legacy baseline ran previously: accuracy{" "}
                {exposure.observed_aggregate_baseline_metrics.accuracy.toFixed(4)}, Brier{" "}
                {exposure.observed_aggregate_baseline_metrics.brier.toFixed(4)}, log loss{" "}
                {exposure.observed_aggregate_baseline_metrics.log_loss.toFixed(4)}.
                Owner-reported rounded aggregates; not recomputed here. This is not
                a pristine holdout. Further evaluation requires explicit owner
                approval of the frozen candidate, protocol and scoring implementation.
              </small>
            </span>
          </div>
        </section>
      </div>
      <section className="panel">
        <PanelTitle
          label="03 / HISTORICAL CHECKS"
          title="Expanding-window backtests"
        />
        <p className="muted">
          Each season is scored by a model fitted only on earlier seasons. The
          architecture was selected using 2023; these are development
          diagnostics, not untouched final tests.
        </p>
        <div
          className="table-scroll"
          role="region"
          aria-label="Scrollable data table"
          tabIndex={0}
        >
          <table>
            <thead>
              <tr>
                <th>Season</th>
                <th>Training games</th>
                <th>Test games</th>
                <th>Accuracy</th>
                <th>Model Brier</th>
                <th>Home Brier</th>
                <th>Log loss</th>
              </tr>
            </thead>
            <tbody>
              {e.backtests.map((b) => (
                <tr key={b.season}>
                  <td>{b.season}</td>
                  <td>{b.train_n}</td>
                  <td>{b.model.n}</td>
                  <td>{pct(b.model.accuracy)}</td>
                  <td>{b.model.brier.toFixed(4)}</td>
                  <td>{b.baseline.brier.toFixed(4)}</td>
                  <td>{b.model.log_loss.toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="panel">
        <PanelTitle
          label="04 / FEATURE CONTRIBUTION"
          title="What happens when a feature is removed?"
        />
        <p className="muted">
          Predeclared ablations of the four-feature candidate. Each removal
          refits on training only. These diagnostics did not create another
          tuned candidate.
        </p>
        <div
          className="table-scroll"
          role="region"
          aria-label="Scrollable data table"
          tabIndex={0}
        >
          <table>
            <thead>
              <tr>
                <th>Removed feature</th>
                <th>Brier score</th>
                <th>Change vs full candidate</th>
                <th>Log loss</th>
              </tr>
            </thead>
            <tbody>
              {e.ablations.map((a) => (
                <tr key={a.removed}>
                  <td>{a.removed.replaceAll("_", " ")}</td>
                  <td>{a.brier.toFixed(4)}</td>
                  <td>
                    {signed(
                      a.brier -
                        e.models.find((m) => m.id === "schedule")!.brier,
                      4,
                    )}
                  </td>
                  <td>{a.log_loss.toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
function Calibration({ data }: { data: Artifact }) {
  const x = (p: number) => 48 + p * 280,
    y = (p: number) => 260 - p * 220;
  return (
    <svg
      className="calibration-chart"
      viewBox="0 0 370 310"
      role="img"
      aria-label="Calibration plot: predicted home win probability versus observed win rate. Exact values are in the expandable table."
    >
      <title>2023 validation calibration</title>
      {[0, 0.25, 0.5, 0.75, 1].map((v) => (
        <g key={v}>
          <line x1={48} y1={y(v)} x2={328} y2={y(v)} stroke="#29342e" />
          <text x={37} y={y(v) + 4} textAnchor="end">
            {v * 100}%
          </text>
          <text x={x(v)} y={279} textAnchor="middle">
            {v * 100}%
          </text>
        </g>
      ))}
      <line
        x1={x(0)}
        y1={y(0)}
        x2={x(1)}
        y2={y(1)}
        stroke="#819389"
        strokeDasharray="5 5"
      />
      {data.evaluation.calibration.map((b) => (
        <circle
          key={b.bin}
          cx={x(b.predicted)}
          cy={y(b.observed)}
          r={Math.max(4, Math.sqrt(b.count) * 1.3)}
          fill="#00e676"
          fillOpacity=".85"
          stroke="#12171a"
          strokeWidth="2"
        >
          <title>
            {pct(b.predicted)} predicted; {pct(b.observed)} observed; n=
            {b.count}
          </title>
        </circle>
      ))}
      <text x={188} y={304} textAnchor="middle">
        Estimated home-win probability
      </text>
      <text x={50} y={22}>
        Observed home-win rate
      </text>
    </svg>
  );
}

function Architecture({ data: d }: { data: Artifact }) {
  const steps = [
    [
      "01",
      Database,
      "Acquire",
      "Public schedules, restricted to 2010–2023. A local snapshot is checksummed.",
    ],
    [
      "02",
      GitBranch,
      "Build features",
      "Earlier-day results only. Team records reset each season.",
    ],
    [
      "03",
      FlaskConical,
      "Train & validate",
      "Fit on 2010–2022. Compare models on the same 2023 games.",
    ],
    [
      "04",
      Target,
      "Generate forecasts",
      "Frozen coefficients produce probabilities and exact explanations.",
    ],
    [
      "05",
      Layers3,
      "Render statically",
      "Validated JSON powers a React interface. No application server.",
    ],
  ] as const;
  return (
    <>
      <PageHeading
        eyebrow="FROM SOURCE TO SCREEN"
        title="Small footprint. Clear lineage."
        text="Offline computation. Deterministic explanations. A static application that can be audited."
      />
      <section className="pipeline">
        {steps.map(([n, Icon, title, text]) => (
          <div className="pipeline-step" key={n}>
            <span className="step-number">{n}</span>
            <Icon size={25} />
            <h2>{title}</h2>
            <p>{text}</p>
          </div>
        ))}
      </section>
      <section className="panel current-limitations">
        <PanelTitle label="CURRENT-SEASON PATH" title="New games. The same frozen model." />
        <p>The stages above describe the historical model build. Current forecasts fetch a separate, season-specific SportsDataverse schedule. Only earlier-date results observed as final before each cutoff enter team state. The frozen feature formulas and coefficients produce a versioned static artifact without fitting a model.</p>
        <p>Missing results, unconfirmed kickoffs and postponed games show an unavailable reason. Source timestamps, exact inputs and artifact checksums appear on the current screen. Current-season performance is established only by reconciling genuinely pregame archived forecasts with later verified results. The postgame screen exposes the scored population, including an honest empty state before those games finish.</p>
        <a href="#current">Inspect Current Week Forecasts <ArrowUpRight size={13} /></a>
      </section>
      <div className="two-column">
        <section className="panel">
          <PanelTitle
            label="DATA LINEAGE"
            title="The receipt behind the result"
          />
          <dl className="lineage">
            <dt>Source</dt>
            <dd>
              <a href={d.attribution.url}>
                nflverse schedules / Lee Sharpe <ArrowUpRight size={13} />
              </a>
            </dd>
            <dt>Retrieved</dt>
            <dd>{d.evaluation.source.retrieved_at}</dd>
            <dt>Model</dt>
            <dd>{d.model.id}</dd>
            <dt>Feature definition</dt>
            <dd>{d.model.feature_version}</dd>
            <dt>Forecast generation</dt>
            <dd>{d.generated_at}</dd>
            <dt>Source SHA256</dt>
            <dd className="hash">{d.model.source_sha256}</dd>
            <dt>Python</dt>
            <dd>{d.evaluation.source.python}</dd>
            <dt>Forecast cutoff</dt>
            <dd>12:00 a.m. Eastern on game day</dd>
          </dl>
          <p className="muted">
            Historical replay uses a current corrected schedule extract. It does
            not prove what the source published at each historical cutoff.
          </p>
        </section>
        <section className="panel">
          <PanelTitle
            label="OPERATING MODEL"
            title="Automation with boundaries"
          />
          <div className="boundary-row">
            <Check size={18} />
            <div>
              <strong>Automated when run locally</strong>
              <p>
                Current-season acquisition, pre-cutoff state, frozen-model scoring,
                immutable archives, result reconciliation, deterministic investigations, static artifacts, schema checks and tests. Challenger training is a separate local research command; holdout evaluation is excluded.
              </p>
            </div>
          </div>
          <div className="boundary-row">
            <ShieldCheck size={18} />
            <div>
              <strong>Owner controlled</strong>
              <p>
                Approve model promotion, unlock holdout evaluation, review source licensing, enable scheduled workflows and authorize publication.
              </p>
            </div>
          </div>
          <div className="boundary-row">
            <LockKeyhole size={18} />
            <div>
              <strong>Prepared, not activated</strong>
              <p>
                Current refresh and GitHub Pages deployment templates. No cloud provisioning,
                schedules, paid APIs or personal website edits.
              </p>
            </div>
          </div>
          <div className="cost-box">
            <strong>
              $0<span>/mo target</span>
            </strong>
            <p>
              Static hosting and local training.
              <br />
              Hosting and CI quotas still apply.
            </p>
          </div>
        </section>
      </div>
      <section className="panel research-design">
        <div>
          <span className="eyebrow">BOUNDED POSTGAME RESEARCH</span>
          <h2>Research assistance, with receipts.</h2>
          <p>
            The local deterministic analyst separates verified result facts, measured forecast error, explanatory hypotheses and demonstrated model limitations. Each verified fact carries a source URL and observation time. Expanded injury, quarterback, weather and news evidence remains unavailable until its source and prediction-time provenance pass review.
          </p>
          <p>
            An LLM may summarize cited evidence. It may not change the model’s
            probabilities. Conflicts, stale reports and missing evidence remain
            explicit.
          </p>
        </div>
        <span className="research-status">
          <LockKeyhole size={16} /> DETERMINISTIC / LOCAL
        </span>
      </section>
      <section className="release-banner">
        <ShieldCheck size={24} />
        <div>
          <strong>Local research build · provisional Tier A</strong>
          <p>
            Public release is NO-GO until the owner approves G0–G4 evidence and
            licensing. The 2024–2025 period is partially exposed; candidate
            evaluation remains locked under a separate frozen protocol.
          </p>
        </div>
      </section>
    </>
  );
}
