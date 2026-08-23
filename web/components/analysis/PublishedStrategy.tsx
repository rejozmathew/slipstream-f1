import type { ReactNode } from "react";

import type {
  AnalyticsSnapshot,
  DriverPublishedStrategy,
  PublishedStrategyBaseline,
  PublishedStrategyOption,
} from "../../domain/protocol";
import { CompoundBadge } from "../shared/CompoundBadge";
import { Panel } from "../shared/Panel";

function rankLabel(rank: PublishedStrategyOption["rank"]) {
  return rank.replaceAll("_", " ");
}

function path(compounds: string[], empty = "—") {
  if (!compounds.length) return <span className="published-path-empty">{empty}</span>;
  return <span className="published-path">{compounds.map((compound, index) => <span key={`${compound}-${index}`}>{index > 0 && <i>→</i>}<CompoundBadge compound={compound} compact /></span>)}</span>;
}

function windows(option: PublishedStrategyOption) {
  const values = option.pitWindows.map((window, index) => window ? `STOP ${index + 1} · L${window.startLap}–${window.endLap}` : `STOP ${index + 1} · WINDOW NOT PUBLISHED`);
  return values.length ? values.join("  ·  ") : "NO PUBLISHED STOP WINDOW";
}

export function PublishedOptionCard({ option, compact = false }: { option: PublishedStrategyOption; compact?: boolean }) {
  return <article className={`published-option${compact ? " published-option-compact" : ""}`}>
    <header><span>{rankLabel(option.rank)}</span><b>{option.stopCount}-STOP</b></header>
    <strong>{path(option.compounds)}</strong>
    <small>{option.order === "ORDERED" ? windows(option) : `${option.order.replaceAll("_", " ")} · NOT SEQUENCE-COMPARABLE`}</small>
    {!compact && option.publishedDeltaSeconds != null && <p>Published delta · +{option.publishedDeltaSeconds.toFixed(1)}s</p>}
    {!compact && option.publishedDeltaSecondsRange && <p>Published delta · +{option.publishedDeltaSecondsRange[0].toFixed(1)}–{option.publishedDeltaSecondsRange[1].toFixed(1)}s</p>}
    {!compact && [...option.conditions, ...option.caveats].map((item) => <p key={item}>{item}</p>)}
  </article>;
}

export function PirelliBaseline({ baseline, compact = false, action }: { baseline?: PublishedStrategyBaseline | null; compact?: boolean; action?: ReactNode }) {
  const present = baseline?.status === "PRESENT";
  return <Panel eyebrow="OFFICIAL PRE-RACE" title="Pirelli baseline" className={`pirelli-baseline${compact ? " pirelli-baseline-compact" : ""}`} action={action ?? (present ? <span className="panel-badge context-ready">PUBLISHED · ADMITTED</span> : undefined)}>
    {!present && <div className="pirelli-unavailable" role="status"><strong>PIRELLI BASELINE UNAVAILABLE</strong><p>{baseline?.reason?.replaceAll("_", " ") ?? "No replay-admissible official source was found for this target session."}</p></div>}
    {present && <div className="pirelli-baseline-body">
      <div className="pirelli-source-row"><span>PIRELLI · PRE-RACE PUBLICATION</span><small>{baseline.publishedAt ? new Date(baseline.publishedAt).toLocaleString() : "PUBLICATION TIME UNAVAILABLE"}</small>{baseline.sourceUrl && <a href={baseline.sourceUrl} target="_blank" rel="noreferrer">SOURCE ↗</a>}</div>
      {baseline.compoundSelection && <div className="physical-nomination"><span>WEEKEND NOMINATION</span><strong><i>H</i>{baseline.compoundSelection.hard}<i>M</i>{baseline.compoundSelection.medium}<i>S</i>{baseline.compoundSelection.soft}</strong></div>}
      <div className="published-options">{baseline.options.length ? baseline.options.map((option) => <PublishedOptionCard key={option.id} option={option} compact={compact} />) : <div className="pirelli-no-options">NO TARGET-SESSION STRATEGY OPTIONS WERE PUBLISHED</div>}</div>
      {!compact && baseline.contextFacts.length > 0 && <div className="pirelli-context-facts">{baseline.contextFacts.slice(0, 3).map((fact) => <p key={`${fact.category}-${fact.statement}`}><span>{fact.category.replaceAll("_", " ")}</span>{fact.statement}</p>)}</div>}
    </div>}
  </Panel>;
}

export function RaceNow({ analytics, compact = false }: { analytics: AnalyticsSnapshot | null; compact?: boolean }) {
  const read = analytics?.raceRead;
  const facts = analytics?.publishedStrategy?.fieldFacts ?? [];
  return <Panel eyebrow="CURRENT SESSION" title="Race now" className={`race-now${compact ? " race-now-compact" : ""}`}>
    {!read && <div className="pirelli-unavailable"><strong>RACE READ UNAVAILABLE</strong><p>Normalized current-session evidence has not reached this cursor.</p></div>}
    {read && <div className="race-now-grid">
      <div><span>RUNNERS</span><strong>{read.population.active}</strong><small>{read.population.terminal} terminal · {read.population.stopped} stopped</small></div>
      <div><span>FIELD SHAPE</span><strong>{read.strategyArchetype.value ?? "NOT ESTABLISHED"}</strong><small>{Object.entries(read.completedStopDistribution).map(([stops, count]) => `${count}×${stops}-stop`).join(" · ") || "NO COMPLETED STOP SHAPE"}</small></div>
      <div><span>DRY RULE</span><strong>{read.dryRequirementLandscape.unsatisfied} NEED SPEC</strong><small>{read.dryRequirementLandscape.unknown} unknown · {read.dryRequirementLandscape.denominator} active</small></div>
      <div className="race-now-facts"><span>NOW</span>{(facts.length ? facts : read.summaryFacts.slice(0, compact ? 1 : 3)).map((fact) => <p key={fact}>{fact}</p>)}</div>
    </div>}
  </Panel>;
}

function relationLabel(relation: DriverPublishedStrategy["relation"]) {
  const labels: Record<DriverPublishedStrategy["relation"], string> = {
    MATCHING_ONE: "MATCHES ONE PUBLISHED OPTION",
    MATCHING_MULTIPLE: "MULTIPLE OPTIONS REMAIN COMPATIBLE",
    DIVERGED: "DIVERGED FROM ORDERED OPTIONS",
    NOT_COMPARABLE: "PUBLISHED ORDER NOT COMPARABLE",
    TERMINAL: "TERMINAL · RETROSPECTIVE ONLY",
    UNKNOWN: "RELATION UNKNOWN",
  };
  return labels[relation];
}

export function DriverPirelliContext({ analytics, driverNumber, compact = false }: { analytics: AnalyticsSnapshot | null; driverNumber: string; compact?: boolean }) {
  const baseline = analytics?.publishedStrategy?.baseline;
  const driver = analytics?.publishedStrategy?.drivers[driverNumber];
  const bank = baseline?.tyreBank.drivers[driverNumber];
  return <Panel eyebrow="PUBLISHED STRATEGY" title="Pirelli context" className={`driver-pirelli-context${compact ? " driver-pirelli-context-compact" : ""}`}>
    {baseline?.status !== "PRESENT" || !driver ? <div className="pirelli-unavailable"><strong>PIRELLI CONTEXT UNAVAILABLE</strong><p>Current-race facts remain available; no published baseline is fabricated.</p></div> : <div className="driver-pirelli-body">
      <div className="driver-pirelli-relation"><span>OBSERVED PATH</span><strong>{path(driver.observedCompounds)}</strong><b data-relation={driver.relation}>{relationLabel(driver.relation)}</b></div>
      <div className="driver-pirelli-windows">{driver.windows.length ? driver.windows.map((window) => <div key={`${window.optionId}-${window.stopIndex}`}><span>{window.optionId} · STOP {window.stopIndex + 1}</span><strong>L{window.startLap}–{window.endLap}</strong><b data-state={window.state}>{window.state}</b></div>) : <div><span>PUBLISHED WINDOW</span><strong>—</strong><b>NO PENDING COMPARABLE WINDOW</b></div>}</div>
      {!compact && driver.facts.length > 0 && <div className="driver-pirelli-facts">{driver.facts.map((fact) => <p key={fact}>{fact}</p>)}</div>}
      {!compact && bank && <div className="driver-tyre-bank"><span>PRE-RACE TYRE BANK</span>{(["hard", "medium", "soft"] as const).map((compound) => <div key={compound}><CompoundBadge compound={compound} compact /><b>{bank[compound].new} NEW</b><small>{bank[compound].used} USED</small></div>)}</div>}
    </div>}
  </Panel>;
}

export function BattlePublishedContext({ analytics, driverNumbers }: { analytics: AnalyticsSnapshot | null; driverNumbers: [string, string] | null }) {
  const baseline = analytics?.publishedStrategy?.baseline;
  if (!driverNumbers || baseline?.status !== "PRESENT") return <div className="panel-empty">PUBLISHED STRATEGY CONTEXT UNAVAILABLE FOR THIS PAIR</div>;
  return <div className="battle-published-context">{driverNumbers.map((number) => {
    const driver = analytics?.publishedStrategy?.drivers[number];
    return <div key={number}><span>CAR {number} · PIRELLI FIT</span><strong>{driver ? relationLabel(driver.relation) : "UNKNOWN"}</strong><div>{driver ? path(driver.observedCompounds) : "—"}</div><small>{driver?.windows[0] ? `L${driver.windows[0].startLap}–${driver.windows[0].endLap} · ${driver.windows[0].state}` : "NO PENDING PUBLISHED WINDOW"}</small></div>;
  })}</div>;
}
