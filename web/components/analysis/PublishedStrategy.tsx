import type { ReactNode } from "react";

import type {
  AnalyticsSnapshot,
  Driver,
  PublishedStrategyBaseline,
  PublishedStrategyOption,
} from "../../domain/protocol";
import {
  actualStrategyCompounds,
  driverPirelliReferenceRows,
  driverPirelliStopWindowsText,
  driverStrategyRelationship,
  dryTyreRequirementText,
  NO_SPECIFIC_PIRELLI_STRATEGY,
  optionDeltaText,
  optionOrderNote,
  optionWindowText,
  prioritizedPirelliContextFacts,
} from "../../domain/pirelliPresentation.mjs";
import { CompoundBadge, CompoundSequence, CompoundTransition } from "../shared/CompoundBadge";
import { Panel } from "../shared/Panel";

function rankLabel(rank: PublishedStrategyOption["rank"]) {
  return rank.replaceAll("_", " ");
}

function compoundCounts(values: Record<string, number>) {
  const entries = Object.entries(values);
  if (!entries.length) return <span className="published-path-empty">—</span>;
  return <span className="published-path compound-counts">{entries.map(([compound, count]) => <span key={compound}><CompoundBadge compound={compound} compact /><b>{count}</b></span>)}</span>;
}

function observedSequences(values: Array<{ sequence: string; drivers: number }> | undefined) {
  if (!values?.length) return <span className="published-path-empty">—</span>;
  return <span className="race-now-sequences">{values.map((item) => <span key={item.sequence}><b>{item.drivers} drivers</b><CompoundSequence compounds={item.sequence.split(/\s*→\s*/)} /></span>)}</span>;
}

export function PublishedOptionCard({ option, compact = false }: { option: PublishedStrategyOption; compact?: boolean }) {
  const orderNote = optionOrderNote(option);
  const delta = optionDeltaText(option);
  return <article className={`published-option${compact ? " published-option-compact" : ""}`}>
    <header><span>{rankLabel(option.rank)}</span><b>{option.stopCount}-STOP</b></header>
    <strong><CompoundSequence compounds={option.compounds} ordered={option.order === "ORDERED"} /></strong>
    <small>{optionWindowText(option)}</small>
    {orderNote && <small>{orderNote}</small>}
    {!compact && delta && <p>{delta}</p>}
    {!compact && [...option.conditions, ...option.caveats].map((item) => <p key={item}>{item}</p>)}
  </article>;
}

export function PirelliNomination({ baseline }: { baseline?: PublishedStrategyBaseline | null }) {
  if (!baseline?.compoundSelection) return null;
  return <div className="physical-nomination"><span>TYRE COMPOUNDS</span><strong><CompoundBadge compound="HARD" compact />{baseline.compoundSelection.hard}<CompoundBadge compound="MEDIUM" compact />{baseline.compoundSelection.medium}<CompoundBadge compound="SOFT" compact />{baseline.compoundSelection.soft}</strong></div>;
}

function unavailableLabel(baseline?: PublishedStrategyBaseline | null) {
  if (baseline?.status === "FETCHING") return "LOADING OFFICIAL PIRELLI STRATEGY…";
  if (baseline?.status === "RETRYING") return "OFFICIAL PIRELLI STRATEGY RETRY SCHEDULED";
  return "NO OFFICIAL PIRELLI STRATEGY AVAILABLE";
}

export function PirelliBaseline({ baseline, fieldFacts = [], compact = false, action }: { baseline?: PublishedStrategyBaseline | null; fieldFacts?: string[]; compact?: boolean; action?: ReactNode }) {
  const present = baseline?.status === "PRESENT";
  return <Panel eyebrow="OFFICIAL PRE-RACE" title="Pirelli tyre strategy" className={`pirelli-baseline${present ? "" : " pirelli-baseline-absent"}${compact ? " pirelli-baseline-compact" : ""}`} action={action ?? (present ? <span className="panel-badge context-ready">{baseline.provenanceLabel ?? "PUBLISHED · MODEL-ADMISSIBLE"}</span> : undefined)}>
    {!present && <div className="pirelli-unavailable pirelli-unavailable-row" role="status"><strong>{unavailableLabel(baseline)}</strong><p>Current race facts remain available.</p></div>}
    {present && <div className="pirelli-baseline-body">
      <div className="pirelli-source-row"><span>PIRELLI · PRE-RACE PUBLICATION</span>{baseline.publishedAt && <small>{new Date(baseline.publishedAt).toLocaleString()}</small>}{baseline.sourceUrl && <a href={baseline.sourceUrl} target="_blank" rel="noreferrer">SOURCE ↗</a>}</div>
      <div className="published-options">{baseline.options.length ? baseline.options.map((option) => <PublishedOptionCard key={option.id} option={option} compact={compact} />) : <div className="pirelli-no-options">{NO_SPECIFIC_PIRELLI_STRATEGY}</div>}</div>
      <PirelliNomination baseline={baseline} />
      {!compact && baseline.contextFacts.length > 0 && <div className="pirelli-context-facts">{prioritizedPirelliContextFacts(baseline.contextFacts, 5).map((fact) => <p key={`${fact.category}-${fact.statement}`}><span>{fact.category.replaceAll("_", " ")}</span>{fact.statement}</p>)}</div>}
      {!compact && fieldFacts.length > 0 && <div className="pirelli-field-facts"><span>CURRENT PIRELLI CONTEXT</span>{fieldFacts.map((fact) => <p key={fact}>{fact}</p>)}</div>}
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
      <div><span>COMPOUND SEQUENCES</span><strong>{observedSequences(analytics?.observedSequences)}</strong><small>Running / in-pit drivers · consecutive repeats summarized</small></div>
      {!compact && <div><span>STINT CONTEXT</span><strong>{stints}</strong><small>Completed stints by compound</small></div>}
      {!compact && <div><span>RECENT PITS</span><strong>{recentPits}</strong><small>Latest factual pit activity</small></div>}
      <div className="race-now-facts"><span>NOW</span>{read.summaryFacts.slice(0, compact ? 1 : 3).map((fact) => <p key={fact}>{fact}</p>)}</div>
    </div>}
  </Panel>;
}

export function DriverPirelliContext({ analytics, driver, compact = false }: { analytics: AnalyticsSnapshot | null; driver: Driver; compact?: boolean }) {
  const baseline = analytics?.publishedStrategy?.baseline;
  const published = analytics?.publishedStrategy?.drivers[driver.number];
  const bank = baseline?.tyreBank.drivers[driver.number];
  const present = baseline?.status === "PRESENT";
  const references = driverPirelliReferenceRows(baseline, published);
  const actual = actualStrategyCompounds(published);
  const dryRule = dryTyreRequirementText(published);
  const contextFact = prioritizedPirelliContextFacts(baseline?.contextFacts ?? [], 1)[0];
  return <Panel eyebrow="DRIVER STRATEGY" title="Tyre strategy" className={`driver-pirelli-context${present ? "" : " driver-pirelli-context-absent"}${compact ? " driver-pirelli-context-compact" : ""}`}>
    <div className="driver-pirelli-body">
      <div className="driver-strategy-current"><div><span>CURRENT TYRE</span><strong><CompoundBadge compound={driver.compound} compact /> {driver.tyre_age == null ? "—" : `${driver.tyre_age}L`}</strong></div><div><span>STOPS</span><strong>{driver.pit_count}</strong></div><div><span>ACTUAL TYRE STRATEGY</span><strong><CompoundSequence compounds={actual} /></strong></div></div>
      {dryRule && <p className={`driver-dry-rule driver-dry-rule-${published?.dryTyreRequirement?.toLowerCase()}`}>{dryRule}</p>}
      {!present ? <div className="pirelli-unavailable pirelli-unavailable-row"><strong>{unavailableLabel(baseline)}</strong><p>Actual driver strategy remains available.</p></div> : <>
        {references.length > 0 ? <><p className="driver-strategy-relationship">{driverStrategyRelationship(baseline, published)}</p><div className="driver-pirelli-routes">{references.map((reference) => <article key={reference.id}><header><span>PIRELLI · {rankLabel(reference.rank)}</span><strong><CompoundSequence compounds={reference.compounds} ordered={reference.ordered} /></strong></header>{reference.assessmentText && <p>{reference.assessmentText}</p>}{reference.orderNote && <p>{reference.orderNote}</p>}<div>{reference.windows.length ? reference.windows.map((window) => <span key={window.stopIndex}><b>STOP {window.stopIndex + 1} · {window.range}</b><small>{window.state}</small></span>) : <span><b>NO STOP LAP PUBLISHED</b></span>}</div></article>)}</div></> : <div className="driver-pirelli-context-only"><strong>{NO_SPECIFIC_PIRELLI_STRATEGY}</strong><PirelliNomination baseline={baseline} />{contextFact && <p><span>{contextFact.category.replaceAll("_", " ")}</span>{contextFact.statement}</p>}</div>}
        {!compact && bank && <div className="driver-tyre-bank"><span>PRE-RACE TYRE BANK</span>{(["hard", "medium", "soft"] as const).map((compound) => <div key={compound}><CompoundBadge compound={compound} compact /><b>{bank[compound].new} NEW</b><small>{bank[compound].used} USED</small></div>)}</div>}</>}
    </div>
  </Panel>;
}

export function BattlePublishedContext({ analytics, drivers }: { analytics: AnalyticsSnapshot | null; drivers: [Driver, Driver] | null }) {
  const baseline = analytics?.publishedStrategy?.baseline;
  if (!drivers) return <div className="panel-empty">SELECT TWO DRIVERS TO COMPARE STRATEGY</div>;
  return <div className="battle-published-context">{drivers.map((raceDriver) => {
    const published = analytics?.publishedStrategy?.drivers[raceDriver.number];
    const dryRule = dryTyreRequirementText(published);
    const present = baseline?.status === "PRESENT";
    const hasOptions = present && baseline.options.length > 0;
    const references = driverPirelliReferenceRows(baseline, published);
    return <div key={raceDriver.number}><span>CAR {raceDriver.number} · ACTUAL TYRE STRATEGY</span><strong><CompoundBadge compound={raceDriver.compound} compact /> {raceDriver.tyre_age == null ? "—" : `${raceDriver.tyre_age}L`} · {raceDriver.pit_count} STOPS</strong><div><small>ACTUAL TYRE STRATEGY</small><CompoundSequence compounds={actualStrategyCompounds(published)} /></div>{dryRule && <p className={`driver-dry-rule driver-dry-rule-${published?.dryTyreRequirement?.toLowerCase()}`}>{dryRule}</p>}{hasOptions ? <><div><small>PIRELLI TYRE STRATEGY</small><b className="strategy-pirelli-options">{references.map((reference) => <CompoundSequence key={reference.id} compounds={reference.compounds} ordered={reference.ordered} />)}</b></div><div><small>PUBLISHED STOP WINDOW</small><b>{driverPirelliStopWindowsText(baseline, published, false)}</b></div><p>{driverStrategyRelationship(baseline, published)}</p></> : <p>{present ? NO_SPECIFIC_PIRELLI_STRATEGY : unavailableLabel(baseline)}</p>}</div>;
  })}{baseline?.status === "PRESENT" && baseline.options.length === 0 && <div className="battle-pirelli-context-only"><PirelliNomination baseline={baseline} /></div>}</div>;
}
