import { useMemo } from "react";

import { Conditions } from "../components/analysis/Conditions";
import { PirelliBaseline, RaceNow, publishedWindowSummary } from "../components/analysis/PublishedStrategy";
import { CompoundBadge } from "../components/shared/CompoundBadge";
import { Panel } from "../components/shared/Panel";
import { driverLifecycle, lifecycleClassName } from "../domain/lifecycle";
import type { AnalyticsSnapshot, RaceState } from "../domain/protocol";

type StrategyViewProps = { state: RaceState; analytics: AnalyticsSnapshot | null; onSelectDriver: (driverNumber: string) => void };

function observedPath(values: string[] | undefined) {
  if (!values?.length) return "—";
  return <span className="published-path">{values.map((value, index) => <span key={`${value}-${index}`}>{index > 0 && <i aria-hidden="true">→</i>}<CompoundBadge compound={value} compact /></span>)}</span>;
}

function pendingWindow(driver: AnalyticsSnapshot["publishedStrategy"]["drivers"][string] | undefined, final: boolean) {
  if (final) return "FINAL";
  return publishedWindowSummary(driver, "—");
}

export function StrategyView({ state, analytics, onSelectDriver }: StrategyViewProps) {
  const drivers = useMemo(() => Object.values(state.drivers).sort((a, b) => (a.position ?? 999) - (b.position ?? 999)), [state.drivers]);
  const final = analytics?.raceRead?.raceLifecycle === "FINAL";
  const baseline = analytics?.publishedStrategy?.baseline;
  const showPublished = baseline?.status === "PRESENT";
  return <div className="strategy-view pirelli-strategy-view">
    <header className="experience-heading strategy-experience-heading"><div><span>RACE INTELLIGENCE</span><h1>Strategy</h1><p>Pirelli’s published pre-race baseline, contextualized by factual current-race evidence.</p></div><div className="strategy-validity-state"><strong>{final ? "FINAL · RETROSPECTIVE" : baseline?.status === "PRESENT" ? "PIRELLI BASELINE · PUBLISHED" : "RACE FACTS"}</strong></div></header>

    <section className={`strategy-foundation${showPublished ? "" : " strategy-foundation-no-pirelli"}`} aria-label="Published strategy and current race context">
      {!showPublished && <div className="strategy-current-column"><RaceNow analytics={analytics} /><Conditions weather={state.weather} session={state.session} /></div>}
      <PirelliBaseline baseline={baseline} compact={!showPublished} />
      {showPublished && <div className="strategy-current-column"><RaceNow analytics={analytics} /><Conditions weather={state.weather} session={state.session} /></div>}
    </section>

    <Panel eyebrow="CURRENT RACE" title="Driver landscape" className="driver-strategy-panel">
      <div className="driver-strategy-scroll"><table className="driver-strategy-table"><thead><tr><th>P</th><th>DRIVER</th><th>TYRE</th><th>AGE</th><th>STOPS</th><th>OBSERVED PATH</th>{showPublished && <><th>PIRELLI FIT</th><th>PUBLISHED WINDOW</th></>}</tr></thead><tbody>{drivers.map((driver) => {
        const lifecycle = driverLifecycle(driver);
        const published = analytics?.publishedStrategy?.drivers[driver.number];
        const relation = published?.relation;
        return <tr key={driver.number} onClick={() => onSelectDriver(driver.number)} className={`clickable ${lifecycleClassName(driver)}`}><td>{driver.position ?? "—"}</td><td><strong>{driver.code ?? driver.number}</strong>{lifecycle.label && <small>{lifecycle.label}</small>}</td><td><CompoundBadge compound={driver.compound} compact /></td><td>{driver.tyre_age ?? "—"}</td><td>{driver.pit_count}</td><td>{observedPath(published?.observedCompounds)}</td>{showPublished && <><td data-relation={relation}>{relation?.replaceAll("_", " ") ?? "—"}</td><td>{pendingWindow(published, final)}</td></>}</tr>;
      })}</tbody></table></div>
    </Panel>
  </div>;
}
