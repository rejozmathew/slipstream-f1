import type { ReactNode } from "react";

import { formatSector } from "../../domain/format";
import { driverLifecycle, lifecycleClassName } from "../../domain/lifecycle";
import type { TowerView } from "../../domain/layout";
import type { AnalyticsSnapshot, Driver, QualifyingIntelligence } from "../../domain/protocol";
import { publishedWindowSummary } from "../analysis/PublishedStrategy";
import { CompoundBadge } from "../shared/CompoundBadge";
import { DataValue } from "../shared/DataValue";
import { Panel } from "../shared/Panel";

export type TimingVariant = "race" | "qualifying" | "practice";

type TimingTowerProps = {
  drivers: Driver[];
  variant: TimingVariant;
  mode?: TowerView;
  analytics?: AnalyticsSnapshot | null;
  replayAvailable: boolean;
  toolbar?: ReactNode;
  onSelectDriver?: (driverNumber: string) => void;
};

function DriverIdentity({ driver }: { driver: Driver }) {
  return <span className="driver-cell">
    <i style={{ backgroundColor: `#${driver.team_colour ?? "77808f"}` }} />
    <b>{driver.code ?? driver.number}</b>
    <span><small>{driver.name?.split(" ").slice(-1)[0] ?? "—"}</small><em>{driver.team ?? "—"}</em></span>
  </span>;
}

function LifecycleValue({ driver }: { driver: Driver }) {
  const lifecycle = driverLifecycle(driver);
  if (lifecycle.label) return <span className="driver-lifecycle-label">{lifecycle.label}</span>;
  return <DataValue compact value={driver.position === 1 ? "LEADER" : driver.interval_to_ahead} availability={driver.availability.interval_to_ahead} />;
}

function RaceCore({ driver }: { driver: Driver }) {
  return <><strong>{driver.position ?? "—"}</strong><DriverIdentity driver={driver} />
    <LifecycleValue driver={driver} />
    <CompoundBadge compound={driver.compound} compact />
  </>;
}

function RaceRow({ driver, onSelect }: { driver: Driver; onSelect?: (driverNumber: string) => void }) {
  const lifecycle = driverLifecycle(driver);
  return <button type="button" className={"timing-row timing-race " + lifecycleClassName(driver)} role="row" onClick={() => onSelect?.(driver.number)}>
    <RaceCore driver={driver} />
    {lifecycle.terminal ? <span>—</span> : <DataValue compact value={driver.position === 1 ? "—" : driver.gap_to_leader} availability={driver.availability.gap_to_leader} />}
    <DataValue compact value={driver.tyre_age} availability={driver.availability.tyre_age} />
    {lifecycle.terminal ? <span>—</span> : <DataValue compact value={driver.last_lap ?? driver.best_lap} availability={driver.availability.last_lap} />}
    <span>{driver.pit_count}</span>
  </button>;
}

function RaceTimingRow({ driver, onSelect }: { driver: Driver; onSelect?: (driverNumber: string) => void }) {
  return <button type="button" className={"timing-row timing-race-timing " + lifecycleClassName(driver)} role="row" onClick={() => onSelect?.(driver.number)}>
    <RaceCore driver={driver} />
    <DataValue compact value={formatSector(driver.sector_1)} availability={driver.availability.sector_1} />
    <DataValue compact value={formatSector(driver.sector_2)} availability={driver.availability.sector_2} />
    <DataValue compact value={formatSector(driver.sector_3)} availability={driver.availability.sector_3} />
    <DataValue compact value={driver.last_lap} availability={driver.availability.last_lap} />
    <DataValue compact value={driver.best_lap} availability={driver.availability.best_lap} />
  </button>;
}

function RaceStrategyRow({ driver, analytics, onSelect }: { driver: Driver; analytics?: AnalyticsSnapshot | null; onSelect?: (driverNumber: string) => void }) {
  const lifecycle = driverLifecycle(driver);
  const published = analytics?.publishedStrategy?.drivers[driver.number];
  return <button type="button" className={"timing-row timing-race-strategy " + lifecycleClassName(driver)} role="row" onClick={() => onSelect?.(driver.number)}>
    <RaceCore driver={driver} />
    <DataValue compact value={driver.tyre_age} availability={driver.availability.tyre_age} />
    <DataValue compact value={driver.stint_laps} availability={driver.availability.stint_laps} />
    <span>{driver.pit_count}</span>
    {lifecycle.terminal ? <span>TERMINAL</span> : <span>{published?.relation.replaceAll("_", " ") ?? "—"}</span>}
    {lifecycle.terminal ? <span>—</span> : <DataValue compact value={publishedWindowSummary(published, "—")} />}
  </button>;
}

function QualifyingRow({ driver, intelligence, onSelect }: { driver: Driver; intelligence?: QualifyingIntelligence; onSelect?: (driverNumber: string) => void }) {
  const lifecycle = driverLifecycle(driver);
  const model = intelligence?.drivers[driver.number];
  const boundary = intelligence?.cutLine.advancePosition === driver.position;
  const delta = model?.benchmarkDelta == null ? "—" : model.benchmarkDelta === 0 ? "BENCHMARK" : `+${model.benchmarkDelta.toFixed(3)}`;
  const cut = model?.cutState === "UNKNOWN" ? "—" : model?.cutState.replaceAll("_", " ") ?? "—";
  return <button type="button" className={`timing-row timing-qualifying ${lifecycleClassName(driver)}${boundary ? " timing-cut-boundary" : ""}`} role="row" onClick={() => onSelect?.(driver.number)}>
    <strong>{driver.position ?? "—"}</strong><DriverIdentity driver={driver} />
    <DataValue compact value={lifecycle.label ?? model?.activity.replaceAll("_", " ")} />
    <DataValue compact value={driver.best_lap ?? driver.last_lap} availability={driver.availability.best_lap} />
    <DataValue compact value={delta} />
    <DataValue compact value={formatSector(driver.sector_1)} availability={driver.availability.sector_1} />
    <DataValue compact value={formatSector(driver.sector_2)} availability={driver.availability.sector_2} />
    <DataValue compact value={formatSector(driver.sector_3)} availability={driver.availability.sector_3} />
    <CompoundBadge compound={driver.compound} compact />
    <span>{driver.tyre_age == null ? "—" : `${driver.tyre_age}L`} · {model?.tyreUsage === "UNKNOWN" ? "—" : model?.tyreUsage ?? "—"}</span>
    <span className={`cut-state cut-${model?.cutState.toLowerCase().replaceAll("_", "-") ?? "unknown"}`}>{cut}</span>
  </button>;
}

function PracticeRow({ driver, onSelect }: { driver: Driver; onSelect?: (driverNumber: string) => void }) {
  return <button type="button" className={"timing-row timing-practice " + lifecycleClassName(driver)} role="row" onClick={() => onSelect?.(driver.number)}>
    <strong>{driver.position ?? "—"}</strong><DriverIdentity driver={driver} />
    <CompoundBadge compound={driver.compound} compact />
    <DataValue compact value={driver.tyre_age} availability={driver.availability.tyre_age} />
    <DataValue compact value={driver.last_lap} availability={driver.availability.last_lap} />
    <DataValue compact value={driver.best_lap} availability={driver.availability.best_lap} />
    <DataValue compact value={driver.stint_laps} availability={driver.availability.stint_laps} />
    <span>{driver.pit_count}</span>
  </button>;
}

const headers = {
  qualifying: ["P", "DRIVER / TEAM", "ACTIVITY", "BEST", "DELTA", "S1", "S2", "S3", "TYRE", "AGE / USAGE", "CUT"],
  practice: ["P", "DRIVER", "TYRE", "AGE", "LAST", "BEST", "STINT", "PIT"],
};

const raceModeHeaders = {
  standard: ["P", "DRIVER", "INT", "TYRE", "GAP", "AGE", "LAST", "PIT"],
  timing: ["P", "DRIVER", "INT", "TYRE", "S1", "S2", "S3", "LAST", "BEST"],
  strategy: ["P", "DRIVER", "INT", "TYRE", "AGE", "STINT", "PIT", "PIRELLI FIT", "PUBLISHED WINDOW"],
};

export function TimingTower({ drivers, variant, mode = "standard", analytics, replayAvailable, toolbar, onSelectDriver }: TimingTowerProps) {
  const headersForView = variant === "race" ? raceModeHeaders[mode] : headers[variant];
  const rowClass = variant === "race" && mode !== "standard" ? `race-${mode}` : variant;
  const qualifying = analytics?.qualifying;
  const qualifierTitle = qualifying?.phase === "UNKNOWN" ? "QUALIFYING · PHASE UNKNOWN" : `QUALIFYING · ${qualifying?.phase ?? "UNKNOWN"}`;
  return <Panel eyebrow={variant === "race" ? "CLASSIFICATION" : variant === "qualifying" ? qualifierTitle : "RUN CLASSIFICATION"} title="Timing tower" action={<div className="panel-actions">{variant === "qualifying" && <strong className="qualifying-clock">{qualifying?.sessionClock ?? "CLOCK UNKNOWN"}</strong>}<span className="panel-badge">{drivers.length} DRIVERS</span>{toolbar}</div>} className="timing-panel">
    {!replayAvailable && <div className="panel-empty">TIMING DATA - UNAVAILABLE</div>}
    {replayAvailable && drivers.length === 0 && <div className="panel-empty">TIMING DATA - UNKNOWN AT THIS SESSION TIME</div>}
    <div className={`timing-table timing-${rowClass}`} role="table">
      <div className={`timing-header timing-${rowClass}`} role="row">{headersForView.map((header) => <span key={header}>{header}</span>)}</div>
      {drivers.map((driver) => variant === "race" && mode === "timing"
        ? <RaceTimingRow driver={driver} onSelect={onSelectDriver} key={driver.number} />
        : variant === "race" && mode === "strategy"
          ? <RaceStrategyRow driver={driver} analytics={analytics} onSelect={onSelectDriver} key={driver.number} />
          : variant === "race"
            ? <RaceRow driver={driver} onSelect={onSelectDriver} key={driver.number} />
            : variant === "qualifying"
              ? <QualifyingRow driver={driver} intelligence={qualifying} onSelect={onSelectDriver} key={driver.number} />
              : <PracticeRow driver={driver} onSelect={onSelectDriver} key={driver.number} />)}
    </div>
  </Panel>;
}

