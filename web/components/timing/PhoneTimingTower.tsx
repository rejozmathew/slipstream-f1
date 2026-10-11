import { useRef, useState, type ReactNode } from "react";
import type { AnalyticsSnapshot, Driver } from "../../domain/protocol";
import { driverClassificationLabel, driverLifecycle, qualifyingEliminated } from "../../domain/lifecycle";
import { CompoundBadge } from "../shared/CompoundBadge";
import { useTowerMotion } from "../../hooks/useTowerMotion";
import type { TimingVariant } from "./TimingTower";
import { TowerRowEffects, towerMotionRowProps } from "./TowerRowEffects";

export function PhoneTimingTower({ drivers, variant, analytics, replayAvailable, timingNotice, intervalsAvailable = false, onSelectDriver, followedDriver }: {
  drivers: Driver[]; variant: TimingVariant; analytics?: AnalyticsSnapshot | null;
  replayAvailable: boolean; timingNotice?: ReactNode; intervalsAvailable?: boolean;
  onSelectDriver?: (number: string) => void; followedDriver?: string | null;
}) {
  const tableRef = useRef<HTMLDivElement>(null);
  useTowerMotion(tableRef, drivers, analytics?.story);
  const choices = variant === "race" ? intervalsAvailable ? ["INT", "GAP"] : ["GAP"] : variant === "qualifying" ? ["TIME", "GAP"] : ["BEST", "GAP", "LAST"];
  const [selection, setSelection] = useState(choices[0]);
  const metric = choices.includes(selection) ? selection : choices[0];
  return <section className="phone-timing" aria-label={`${variant} timing`}>
    <header><div><strong>TIMING</strong><span>tap a driver</span></div><div className="phone-metric-switch" role="group" aria-label="Timing value">{choices.map((item) => <button aria-pressed={metric === item} onClick={() => setSelection(item)} key={item}>{item}</button>)}</div></header>
    <div className="phone-timing-labels" aria-hidden="true"><span>P</span><span>DRIVER</span><span>{metric}</span><span>TYRE</span></div>
    {!replayAvailable && (timingNotice ?? <p className="panel-empty">TIMING DATA NOT AVAILABLE FOR THIS SESSION</p>)}
    {replayAvailable && drivers.length === 0 && <p className="panel-empty">NO TIMING ROWS YET</p>}
    <div ref={tableRef} data-motion-variant={variant} data-motion-cut={analytics?.qualifying?.cutLine?.status === "AVAILABLE" && ["Q1", "Q2", "SQ1", "SQ2"].includes(analytics.qualifying.phase) ? analytics.qualifying.cutLine.advancePosition : undefined} className="phone-timing-rows">{drivers.map((driver) => {
      const lifecycle = driverLifecycle(driver);
      const q = analytics?.qualifying?.drivers[driver.number];
      const eliminated = variant === "qualifying" && qualifyingEliminated(driver, q);
      const status = (eliminated ? q?.qStatus ?? "ELIMINATED" : null) ?? driverClassificationLabel(driver) ?? lifecycle.label;
      let value: string | number | null | undefined;
      if (variant === "race") value = (lifecycle.status === "FINISHED" ? null : status) || (metric === "INT" ? driver.position === 1 ? null : driver.interval_to_ahead : driver.position === 1 ? "LEADER" : driver.gap_to_leader);
      else if (variant === "qualifying") value = metric === "TIME" ? q?.scopeBest : q?.benchmarkDelta == null ? null : q.benchmarkDelta === 0 ? "LEADER" : `+${q.benchmarkDelta.toFixed(3)}`;
      else value = metric === "GAP" ? driver.best_lap_delta_to_leader : metric === "LAST" ? driver.last_lap : driver.best_lap;
      if (typeof value === "string" && !value.trim()) value = null;
      return <button data-driver-number={driver.number} {...towerMotionRowProps(driver)} className={`phone-timing-row${followedDriver === driver.number ? " is-followed" : ""}${eliminated ? " qualifying-eliminated" : ""}`} key={driver.number} onClick={() => onSelectDriver?.(driver.number)} aria-label={`P${driver.position ?? "—"} ${driver.name ?? driver.code ?? driver.number}, ${metric} ${value ?? "—"}${status ? `, ${status}` : ""}${driver.team ? `, ${driver.team}` : ""}`}>
        <span className="phone-position">{driver.position ?? "—"}</span><span className="phone-identity" style={{ borderColor: `#${driver.team_colour ?? "77808f"}` }}><span><b>{followedDriver === driver.number ? "★ " : ""}{driver.code ?? driver.number}</b>{status && <em className="phone-state-badge" title={status}>{status}</em>}</span><small>{driver.team || "—"}</small></span><strong className={`phone-primary-value${["TIME", "BEST", "LAST"].includes(metric) ? " tower-time" : ""}`}>{value ?? "—"}</strong><span className="phone-tyre"><CompoundBadge compound={driver.compound} compact /><small>{driver.tyre_age == null ? "—" : `${driver.tyre_age}L`}</small></span>
        <TowerRowEffects />
      </button>;
    })}</div>
  </section>;
}
