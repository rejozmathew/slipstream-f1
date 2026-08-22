import { useMemo } from "react";

import { Panel } from "../components/shared/Panel";
import { CompoundBadge } from "../components/shared/CompoundBadge";
import { StrategyOutlook } from "../components/analysis/StrategyOutlook";
import { driverLifecycle, lifecycleClassName } from "../domain/lifecycle";
import type { AnalyticsSnapshot, RaceState } from "../domain/protocol";

type StrategyViewProps = { state: RaceState; analytics: AnalyticsSnapshot | null; onSelectDriver: (driverNumber: string) => void };

function distribution(value: Record<string, number> | undefined) {
  if (!value || Object.keys(value).length === 0) return "—";
  return Object.entries(value).map(([label, count]) => `${label} ${count}`).join(" · ");
}

function stopDistribution(value: Record<string, number> | undefined) {
  if (!value || Object.keys(value).length === 0) return "—";
  return Object.entries(value).map(([stops, drivers]) => `${drivers} ${stops}-stop`).join(" · ");
}
export function StrategyView({ state, analytics, onSelectDriver }: StrategyViewProps) {
  const drivers = useMemo(() => Object.values(state.drivers).sort((a, b) => (a.position ?? 999) - (b.position ?? 999)), [state.drivers]);
  const read = analytics?.raceRead;
  const final = analytics?.strategyLifecycle === "FINAL";
  const context = analytics?.context;
  return <div className="strategy-view">
    <header className="experience-heading"><div><span>RACE INTELLIGENCE</span><h1>Strategy</h1><p>{final ? "Retrospective field read at the chequered flag." : "Field facts first; future outlook appears only when every gate passes."}</p></div><div className="strategy-validity-state"><strong>{final ? "FINAL · RETROSPECTIVE" : analytics?.projectionGate?.publishAllowed ? "OUTLOOK · VALID" : "OUTLOOK · WITHHELD"}</strong></div></header>

    <section className="strategy-band strategy-race-read" aria-label="Race Read">
      <div className="strategy-band-heading"><span>01</span><h2>Race Read</h2><small>SERVER AUTHORED</small></div>
      {!read && <div className="panel-empty">RACE READ UNAVAILABLE AT THIS CURSOR</div>}
      {read && <div className="race-read-facts">{read.summaryFacts.length > 0 ? read.summaryFacts.map((fact) => <p key={fact}>{fact}</p>) : <p>No unusual field fact is established yet.</p>}</div>}
    </section>

    <div className="strategy-overview-grid">
      <Panel eyebrow="FIELD SHAPE" title="02 · Field shape"><div className="strategy-compact-grid"><div><span>STARTING TYRES</span><strong>{distribution(read?.startingTyreDistribution)}</strong><small>{analytics?.startingTyrePopulation?.known ?? 0}/{analytics?.startingTyrePopulation?.participants ?? 0} known starters</small></div><div><span>CURRENT TYRES</span><strong>{distribution(read?.currentTyreDistribution)}</strong><small>{analytics?.currentTyrePopulation?.known ?? 0}/{analytics?.currentTyrePopulation?.active ?? 0} active known</small></div><div><span>COMPLETED STOPS</span><strong>{stopDistribution(read?.completedStopDistribution)}</strong></div><div><span>OBSERVED ARCHETYPE</span><strong>{read?.strategyArchetype.value ?? "NOT ESTABLISHED"}</strong><small>{read?.strategyArchetype.status ?? "UNKNOWN"}</small></div></div></Panel>
      <Panel eyebrow="PACE & STINTS" title="03 · Pace & stints"><div className="strategy-compact-grid"><div><span>PACE FADE</span><strong>{read ? `${read.paceTrendDistribution.highFade} high · ${read.paceTrendDistribution.moderateFade} moderate` : "—"}</strong><small>{read?.paceTrendDistribution.comparableDrivers ?? 0}/{read?.paceTrendDistribution.denominator ?? 0} comparable current-race drivers</small></div><div><span>STINT EVIDENCE</span><strong>{read ? Object.entries(read.stintContextByCompound).map(([compound, item]) => `${compound} ${item.completedStints}`).join(" · ") || "—" : "—"}</strong><small>completed same-race stints</small></div></div></Panel>
      <Panel eyebrow="CONSTRAINTS" title="04 · Constraints"><div className="strategy-compact-grid"><div><span>DRY RULE</span><strong>{read ? `${read.dryRequirementLandscape.unsatisfied} unsatisfied · ${read.dryRequirementLandscape.unknown} unknown` : "—"}</strong><small>one backend population · {read?.dryRequirementLandscape.denominator ?? 0} active</small></div><div><span>NET PIT LOSS</span><strong>{analytics?.netPitLoss?.status ?? "UNKNOWN"}</strong><small>free stop, rejoin and quantified undercut remain blocked</small></div><div><span>PROJECTION GATE</span><strong>{analytics?.projectionGate?.publishAllowed ? "PASS" : final ? "FINAL" : "WITHHELD"}</strong><small>{analytics?.projectionGate?.stability.status ?? "UNAVAILABLE"} stability</small></div></div></Panel>
      <Panel eyebrow="CONTEXT" title="05 · Context"><div className="strategy-compact-grid"><div><span>WEEKEND CONTEXT</span><strong>{context?.status.toUpperCase() ?? "UNAVAILABLE"}</strong><small>{context?.status === "ready" ? `${context.sessionCount} earlier same-meeting sessions` : "No eligible same-meeting evidence is loaded"}</small></div><div><span>OFFICIAL PRE-RACE</span><strong>{analytics?.officialPreRace?.status ?? "ABSENT"}</strong><small>{analytics?.officialPreRace?.reason ?? "No attributed source"}</small></div><div><span>HISTORICAL</span><strong>{analytics?.historical?.status ?? "ABSENT"}</strong><small>{analytics?.historical?.reason ?? "Not mixed into current-race truth"}</small></div></div></Panel>
    </div>

    <Panel eyebrow="DRIVERS" title="06 · Driver strategy landscape" className="driver-strategy-panel"><div className="driver-strategy-scroll"><table className="driver-strategy-table"><thead><tr><th>P</th><th>DRIVER</th><th>TYRE</th><th>AGE</th><th>STOPS</th><th>RULE</th><th>PACE TREND</th><th>STATUS / PLAN</th></tr></thead><tbody>{drivers.map((driver) => {
      const lifecycle = driverLifecycle(driver);
      const strategy = analytics?.drivers[driver.number]?.strategy;
      const trend = strategy?.paceTrend ?? strategy?.degradation;
      const window = strategy?.pitWindow.value;
      const plan = lifecycle.label ?? (final ? "FINAL" : strategy?.disposition === "TO_FINISH" ? "TO FLAG" : Array.isArray(window) ? `L${window[0]}–${window[1]}` : "—");
      return <tr key={driver.number} onClick={() => onSelectDriver(driver.number)} className={`clickable ${lifecycleClassName(driver)}`}><td>{driver.position ?? "—"}</td><td>{driver.code ?? driver.number}</td><td><CompoundBadge compound={driver.compound} compact /></td><td>{driver.tyre_age ?? "—"}</td><td>{driver.pit_count}</td><td>{strategy?.dryTyreRequirement === "SATISFIED" ? "✓ SATISFIED" : strategy?.dryTyreRequirement === "UNSATISFIED" ? "! SPEC NEEDED" : "—"}</td><td>{trend?.value == null ? "—" : `${trend.value} s/lap`}</td><td>{plan}</td></tr>;
    })}</tbody></table></div></Panel>

    <section className="strategy-outlook-section"><div className="strategy-band-heading"><span>07</span><h2>Outlook</h2><small>{final ? "RETROSPECTIVE" : "GATED"}</small></div><StrategyOutlook analytics={analytics} /></section>
  </div>;
}
