import type { ReactNode } from "react";

import type {
  AnalyticsSnapshot,
  DriverPublishedStrategy,
  PublishedStrategyBaseline,
  PublishedStrategyOption,
} from "../../domain/protocol";
import { CompoundBadge, CompoundTransition } from "../shared/CompoundBadge";
import { Panel } from "../shared/Panel";

function rankLabel(rank: PublishedStrategyOption["rank"]) {
  return rank.replaceAll("_", " ");
}

function path(compounds: string[], empty = "—", ordered = true) {
  if (!compounds.length) return <span className="published-path-empty">{empty}</span>;
  return <span className="published-path">{compounds.map((compound, index) => <span key={`${compound}-${index}`}>{index > 0 && <i>{ordered ? "→" : "+"}</i>}<CompoundBadge compound={compound} compact /></span>)}</span>;
}

function compoundCounts(values: Record<string, number>) {
  const entries = Object.entries(values);
  if (!entries.length) return <span className="published-path-empty">—</span>;
  return <span className="published-path compound-counts">{entries.map(([compound, count]) => <span key={compound}><CompoundBadge compound={compound} compact /><b>{count}</b></span>)}</span>;
}

function observedSequences(values: Array<{ sequence: string; drivers: number }> | undefined) {
  if (!values?.length) return <span className="published-path-empty">—</span>;
  return <span className="race-now-sequences">{values.map((item) => <span key={item.sequence}><b>{item.drivers} drivers</b>{path(item.sequence.split(/\s*→\s*/))}</span>)}</span>;
}

export function publishedWindowSummary(driver: DriverPublishedStrategy | undefined, empty = "NO PENDING PUBLISHED WINDOW") {
  if (!driver?.windows.length) return empty;
  const options = new Set(driver.windows.map((window) => window.optionId)).size;
  const details = driver.windows.map((window) => `${window.optionId} L${window.startLap}–${window.endLap} ${window.state}`).join(" · ");
  return options > 1 ? `${options} OPTIONS · ${details}` : details;
}

function windows(option: PublishedStrategyOption) {
  const values = option.pitWindows.map((window, index) => window ? `STOP ${index + 1} · L${window.startLap}–${window.endLap}` : `STOP ${index + 1} · WINDOW NOT PUBLISHED`);
  return values.length ? values.join("  ·  ") : "NO PUBLISHED STOP WINDOW";
}

export function PublishedOptionCard({ option, compact = false }: { option: PublishedStrategyOption; compact?: boolean }) {
  return <article className={`published-option${compact ? " published-option-compact" : ""}`}>
    <header><span>{rankLabel(option.rank)}</span><b>{option.stopCount}-STOP</b></header>
    <strong>{path(option.compounds, "—", option.order === "ORDERED")}</strong>
    <small>{option.order === "ORDERED" ? windows(option) : `${option.order.replaceAll("_", " ")} · NOT SEQUENCE-COMPARABLE`}</small>
    {!compact && option.publishedDeltaSeconds != null && <p>Published delta · +{option.publishedDeltaSeconds.toFixed(1)}s</p>}
    {!compact && option.publishedDeltaSecondsRange && <p>Published delta · +{option.publishedDeltaSecondsRange[0].toFixed(1)}–{option.publishedDeltaSecondsRange[1].toFixed(1)}s</p>}
    {!compact && [...option.conditions, ...option.caveats].map((item) => <p key={item}>{item}</p>)}
  </article>;
}

export function PirelliBaseline({ baseline, compact = false, action }: { baseline?: PublishedStrategyBaseline | null; compact?: boolean; action?: ReactNode }) {
  const present = baseline?.status === "PRESENT";
  return <Panel eyebrow="OFFICIAL PRE-RACE" title="Pirelli baseline" className={`pirelli-baseline${present ? "" : " pirelli-baseline-absent"}${compact ? " pirelli-baseline-compact" : ""}`} action={action ?? (present ? <span className="panel-badge context-ready">{baseline.provenanceLabel ?? "PUBLISHED · MODEL-ADMISSIBLE"}</span> : undefined)}>
    {!present && <div className="pirelli-unavailable pirelli-unavailable-row" role="status"><strong>PIRELLI CONTEXT NOT AVAILABLE</strong><p>Race facts remain primary.</p></div>}
    {present && <div className="pirelli-baseline-body">
      <div className="pirelli-source-row"><span>PIRELLI · PRE-RACE PUBLICATION</span>{baseline.publishedAt && <small>{new Date(baseline.publishedAt).toLocaleString()}</small>}{baseline.sourceUrl && <a href={baseline.sourceUrl} target="_blank" rel="noreferrer">SOURCE ↗</a>}</div>
      {baseline.compoundSelection && <div className="physical-nomination"><span>WEEKEND NOMINATION</span><strong><CompoundBadge compound="HARD" compact />{baseline.compoundSelection.hard}<CompoundBadge compound="MEDIUM" compact />{baseline.compoundSelection.medium}<CompoundBadge compound="SOFT" compact />{baseline.compoundSelection.soft}</strong></div>}
      <div className="published-options">{baseline.options.length ? baseline.options.map((option) => <PublishedOptionCard key={option.id} option={option} compact={compact} />) : <div className="pirelli-no-options">NO TARGET-SESSION STRATEGY OPTIONS WERE PUBLISHED</div>}</div>
      {!compact && baseline.contextFacts.length > 0 && <div className="pirelli-context-facts">{baseline.contextFacts.slice(0, 3).map((fact) => <p key={`${fact.category}-${fact.statement}`}><span>{fact.category.replaceAll("_", " ")}</span>{fact.statement}</p>)}</div>}
    </div>}
  </Panel>;
}

export function RaceNow({ analytics, compact = false }: { analytics: AnalyticsSnapshot | null; compact?: boolean }) {
  const read = analytics?.raceRead;
  const lifecycleCounts = read ? [
    [read.population.inPit, "in pit"],
    [read.population.stopped, "stopped"],
    [read.population.retired, "retired / out"],
    [read.population.unconfirmed, "status unknown"],
    [read.population.finished, "finished"],
    [read.population.dnf, "DNF"],
    [read.population.dns, "DNS"],
    [read.population.dsq, "DSQ"],
  ].filter(([count]) => Number(count) > 0).map(([count, label]) => `${count} ${label}`).join(" · ") : "";
  const stopDistribution = read ? Object.entries(read.completedStopDistribution).map(([stops, count]) => `${stops} ${stops === "1" ? "stop" : "stops"}: ${count}`).join(" · ") || "—" : "—";
  const stints = read && Object.keys(read.stintContextByCompound).length ? <span className="race-now-compound-list">{Object.entries(read.stintContextByCompound).map(([compound, value]) => <span key={compound}><CompoundBadge compound={compound} compact /><b>{value.completedStints} stints · median {value.medianLife.toFixed(1)}L</b></span>)}</span> : "—";
  const recentPits = read?.recentPitActivity.length ? <span className="race-now-compound-list">{read.recentPitActivity.slice(-3).map((pit) => <span key={`${pit.driverNumber}-${pit.lap}`}><b>#{pit.driverNumber} · L{pit.lap}</b><CompoundTransition from={pit.previousCompound} to={pit.newCompound} compact /></span>)}</span> : "—";
  return <Panel eyebrow="CURRENT SESSION" title="Race now" className={`race-now${compact ? " race-now-compact" : ""}`}>
    {!read && <div className="pirelli-unavailable"><strong>RACE READ NOT YET AVAILABLE</strong><p>Current race facts will appear as the session develops.</p></div>}
    {read && <div className="race-now-grid">
      <div><span>RUNNING / RECENT PROGRESS</span><strong>{read.population.running} RUNNING</strong><small>{lifecycleCounts}</small></div>
      <div><span>CURRENT TYRES</span><strong>{compoundCounts(read.currentTyreDistribution)}</strong><small>Factually running or in-pit drivers</small></div>
      <div><span>COMPLETED STOPS</span><strong>{stopDistribution}</strong><small>Observed stop-count distribution</small></div>
      <div><span>DRY RULE</span><strong>{read.dryRequirementLandscape.unsatisfied} drivers still need another dry compound</strong><small>{read.dryRequirementLandscape.unknown} unknown · {read.dryRequirementLandscape.denominator} running or in pit</small></div>
      <div><span>PACE CONTEXT</span><strong>{read.paceTrendDistribution.comparableDrivers} COMPARABLE</strong><small>{read.paceTrendDistribution.highFade} high fade · {read.paceTrendDistribution.moderateFade} moderate · {read.paceTrendDistribution.lowOrStable} stable</small></div>
      <div><span>OBSERVED SEQUENCES</span><strong>{observedSequences(analytics?.observedSequences)}</strong><small>Active running / in-pit compound paths</small></div>
      {!compact && <div><span>STINT CONTEXT</span><strong>{stints}</strong><small>Completed stints by compound</small></div>}
      {!compact && <div><span>RECENT PITS</span><strong>{recentPits}</strong><small>Latest factual pit activity</small></div>}
      <div className="race-now-facts"><span>NOW</span>{read.summaryFacts.slice(0, compact ? 1 : 3).map((fact) => <p key={fact}>{fact}</p>)}</div>
    </div>}
  </Panel>;
}

function relationLabel(relation: DriverPublishedStrategy["relation"]) {
  const labels: Record<DriverPublishedStrategy["relation"], string> = {
    MATCHING_ONE: "MATCHES ONE PUBLISHED OPTION",
    MATCHING_MULTIPLE: "MULTIPLE OPTIONS REMAIN COMPATIBLE",
    DIVERGED: "DIVERGED FROM ORDERED OPTIONS",
    NOT_COMPARABLE: "PUBLISHED ORDER NOT COMPARABLE",
    TERMINAL: "FINAL · RETROSPECTIVE ONLY",
    UNKNOWN: "—",
  };
  return labels[relation];
}

export function DriverPirelliContext({ analytics, driverNumber, compact = false }: { analytics: AnalyticsSnapshot | null; driverNumber: string; compact?: boolean }) {
  const baseline = analytics?.publishedStrategy?.baseline;
  const driver = analytics?.publishedStrategy?.drivers[driverNumber];
  const bank = baseline?.tyreBank.drivers[driverNumber];
  const present = baseline?.status === "PRESENT" && driver;
  return <Panel eyebrow="PUBLISHED STRATEGY" title="Pirelli context" className={`driver-pirelli-context${present ? "" : " driver-pirelli-context-absent"}${compact ? " driver-pirelli-context-compact" : ""}`}>
    {!present ? <div className="pirelli-unavailable pirelli-unavailable-row"><strong>PIRELLI CONTEXT NOT AVAILABLE</strong><p>Driver facts remain primary.</p></div> : <div className="driver-pirelli-body">
      <div className="driver-pirelli-relation"><span>OBSERVED PATH</span><strong>{path(driver.observedCompounds)}</strong><b data-relation={driver.relation}>{relationLabel(driver.relation)}</b></div>
      <div className="driver-pirelli-windows">{driver.windows.length ? driver.windows.map((window) => <div key={`${window.optionId}-${window.stopIndex}`}><span>{window.optionId} · STOP {window.stopIndex + 1}</span><strong>L{window.startLap}–{window.endLap}</strong><b data-state={window.state}>{window.state}</b></div>) : <div><span>PUBLISHED WINDOW</span><strong>—</strong><b>NO PENDING COMPARABLE WINDOW</b></div>}</div>
      {!compact && driver.facts.length > 0 && <div className="driver-pirelli-facts">{driver.facts.map((fact) => <p key={fact}>{fact}</p>)}</div>}
      {!compact && bank && <div className="driver-tyre-bank"><span>PRE-RACE TYRE BANK</span>{(["hard", "medium", "soft"] as const).map((compound) => <div key={compound}><CompoundBadge compound={compound} compact /><b>{bank[compound].new} NEW</b><small>{bank[compound].used} USED</small></div>)}</div>}
    </div>}
  </Panel>;
}

export function BattlePublishedContext({ analytics, driverNumbers }: { analytics: AnalyticsSnapshot | null; driverNumbers: [string, string] | null }) {
  const baseline = analytics?.publishedStrategy?.baseline;
  if (!driverNumbers || baseline?.status !== "PRESENT") return <div className="panel-empty">NO PUBLISHED PIRELLI CONTEXT FOR THIS PAIR</div>;
  return <div className="battle-published-context">{driverNumbers.map((number) => {
    const driver = analytics?.publishedStrategy?.drivers[number];
    return <div key={number}><span>CAR {number} · PIRELLI FIT</span><strong>{driver ? relationLabel(driver.relation) : "—"}</strong><div>{driver ? path(driver.observedCompounds) : "—"}</div><small>{publishedWindowSummary(driver)}</small></div>;
  })}</div>;
}
