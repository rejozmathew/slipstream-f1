import { useRef } from "react";
import type { AnalyticsSnapshot, Driver } from "../../domain/protocol";
import { driverClassificationLabel, driverLifecycle } from "../../domain/lifecycle";
import { useTowerMotion } from "../../hooks/useTowerMotion";
import { CompoundBadge } from "../shared/CompoundBadge";
import { TowerRowEffects, towerMotionRowProps } from "./TowerRowEffects";
import "./secondary-timing-rail.css";

export function SecondaryTimingRail({ drivers, analytics, onSelect, variant }: { drivers: Driver[]; analytics: AnalyticsSnapshot | null; onSelect: (number: string) => void; variant: string }) {
  const table = useRef<HTMLDivElement>(null);
  const ordered = [...drivers].sort((a, b) => (a.position ?? 999) - (b.position ?? 999));
  useTowerMotion(table, drivers, analytics?.story);
  return <aside className="secondary-timing-rail" aria-label="Timing tower">
    <h2>TIMING TOWER</h2>
    <div ref={table} role="table" aria-label="Session order" data-motion-variant={variant}>
      <div className="secondary-rail-row secondary-rail-header" role="row"><span>P</span><span>DRIVER</span><span>INT</span><span>TYRE</span></div>
      {ordered.map(driver => {
        const lifecycle = driverLifecycle(driver);
        const status = driverClassificationLabel(driver) || (lifecycle.retiredIndicated ? "RETIRED" : lifecycle.stopped ? "STOPPED" : lifecycle.inPit ? "IN PIT" : null);
        return <button key={driver.number} className="timing-row secondary-rail-row" role="row" data-driver-number={driver.number} {...towerMotionRowProps(driver)} onClick={() => onSelect(driver.number)}>
          <strong>{driver.position ?? "—"}</strong><b className="secondary-rail-driver"><i />{driver.code ?? driver.number}</b>
          <span className={status ? "secondary-rail-status" : ""}>{status ?? (driver.position === 1 ? "—" : driver.interval_to_ahead ?? "—")}</span>
          <span className="secondary-rail-tyre"><CompoundBadge compound={driver.compound} compact /><small>{driver.tyre_age == null ? "—" : `${driver.tyre_age}L`}</small></span><TowerRowEffects />
        </button>;
      })}
    </div>
  </aside>;
}
