import { useEffect, useId, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { useTowerMotion } from "../../hooks/useTowerMotion";
import { fitTowerColumns, fittedTowerRowHeight } from "./towerColumns";

import { formatLapTime, formatSector } from "../../domain/format";
import { driverClassificationLabel, driverLifecycle, lifecycleClassName } from "../../domain/lifecycle";
import type { TowerView } from "../../domain/layout";
import type { AnalyticsSnapshot, Driver, QualifyingIntelligence } from "../../domain/protocol";
import { actualStrategyCompounds } from "../../domain/pirelliPresentation.mjs";
import { lapDeficitGap } from "../../domain/correctness.mjs";
import { CompoundBadge, CompoundSequence } from "../shared/CompoundBadge";
import { DataValue } from "../shared/DataValue";
import { Panel } from "../shared/Panel";

export type TimingVariant = "race" | "qualifying" | "practice";

type TimingTowerProps = {
  drivers: Driver[];
  variant: TimingVariant;
  mode?: TowerView;
  analytics?: AnalyticsSnapshot | null;
  replayAvailable: boolean;
  sectorTimingAvailable?: boolean;
  intervalsAvailable?: boolean;
  desktopRaceColumns?: boolean;
  compact?: boolean;
  tvScale?: number;
  toolbar?: ReactNode;
  onSelectDriver?: (driverNumber: string) => void;
};

function DriverIdentity({ driver, secondaryLabel }: { driver: Driver; secondaryLabel?: string }) {
  return <span className="driver-cell">
    <i style={{ backgroundColor: `#${driver.team_colour ?? "77808f"}` }} />
    <b>{driver.code ?? driver.number}</b>
    <span><small>{driver.name?.split(" ").slice(-1)[0] ?? "—"}</small><em>{secondaryLabel ?? driver.team ?? "—"}</em></span>
  </span>;
}

function LifecycleValue({ driver, leader }: { driver: Driver; leader?: Driver }) {
  const lifecycle = driverLifecycle(driver);
  const classification = driverClassificationLabel(driver);
  if (classification) return <span className="driver-lifecycle-label">{classification}</span>;
  if (lifecycle.retiredIndicated) return <span className="driver-lifecycle-label">RETIRED</span>;
  if (lifecycle.stopped) return <span className="driver-lifecycle-label">STOPPED</span>;
  if (lifecycle.inPit) return <span className="driver-lifecycle-label">IN PIT</span>;
  const lapDeficit = lapDeficitGap(driver, leader);
  if (lapDeficit) return <span>{lapDeficit}</span>;
  return <DataValue compact value={driver.position === 1 ? "LEADER" : driver.gap_to_leader} availability={driver.availability.gap_to_leader} />;
}

function RaceCore({ driver, leader, intervalsAvailable = false }: { driver: Driver; leader?: Driver; intervalsAvailable?: boolean }) {
  const lifecycle = driverLifecycle(driver);
  const showInterval = driver.position != null && driver.position > 1 && (lifecycle.circulating || lifecycle.status === "FINISHED");
  return <><strong>{driver.position ?? "—"}</strong><DriverIdentity driver={driver} />
    <LifecycleValue driver={driver} leader={leader} />
    {intervalsAvailable && <DataValue compact value={showInterval ? driver.interval_to_ahead : null} availability={driver.availability.interval_to_ahead} />}
    <CompoundBadge compound={driver.compound} compact />
  </>;
}

function RaceRow({ driver, leader, intervalsAvailable, compact = false, onSelect }: { driver: Driver; leader?: Driver; intervalsAvailable: boolean; compact?: boolean; onSelect?: (driverNumber: string) => void }) {
  const lifecycle = driverLifecycle(driver);
  return <button type="button" className={`timing-row timing-race${intervalsAvailable ? " timing-with-interval" : ""} ${lifecycleClassName(driver)}`} role="row" data-driver-number={driver.number} onClick={() => onSelect?.(driver.number)}>
    <RaceCore driver={driver} leader={leader} intervalsAvailable={intervalsAvailable} />
    {!compact && <DataValue compact value={driver.tyre_age} availability={driver.availability.tyre_age} />}
    {!compact && (lifecycle.terminal ? <span>—</span> : <DataValue compact value={driver.last_lap ?? driver.best_lap} availability={driver.availability.last_lap} />)}
    <span>{driver.pit_count}</span>
  </button>;
}

function RaceTimingRow({ driver, leader, intervalsAvailable, onSelect }: { driver: Driver; leader?: Driver; intervalsAvailable: boolean; onSelect?: (driverNumber: string) => void }) {
  return <button type="button" className={`timing-row timing-race-timing${intervalsAvailable ? " timing-with-interval" : ""} ${lifecycleClassName(driver)}`} role="row" data-driver-number={driver.number} onClick={() => onSelect?.(driver.number)}>
    <RaceCore driver={driver} leader={leader} intervalsAvailable={intervalsAvailable} />
    <DataValue compact value={formatSector(driver.sector_1)} availability={driver.availability.sector_1} />
    <DataValue compact value={formatSector(driver.sector_2)} availability={driver.availability.sector_2} />
    <DataValue compact value={formatSector(driver.sector_3)} availability={driver.availability.sector_3} />
    <DataValue compact value={driver.last_lap} availability={driver.availability.last_lap} />
    <DataValue compact value={driver.best_lap} availability={driver.availability.best_lap} />
  </button>;
}

function RaceStrategyRow({ driver, leader, intervalsAvailable, analytics, onSelect }: { driver: Driver; leader?: Driver; intervalsAvailable: boolean; analytics?: AnalyticsSnapshot | null; onSelect?: (driverNumber: string) => void }) {
  const published = analytics?.publishedStrategy?.drivers[driver.number];
  const lastStop = published?.actualStrategy?.stopLaps.at(-1);
  return <button type="button" className={`timing-row timing-race-strategy timing-race-strategy-detail${intervalsAvailable ? " timing-with-interval" : ""} ${lifecycleClassName(driver)}`} role="row" data-driver-number={driver.number} onClick={() => onSelect?.(driver.number)}>
    <RaceCore driver={driver} leader={leader} intervalsAvailable={intervalsAvailable} />
    <DataValue compact value={driver.tyre_age} availability={driver.availability.tyre_age} />
    <DataValue compact value={driver.stint_laps} availability={driver.availability.stint_laps} />
    <span>{driver.pit_count}</span>
    <CompoundSequence compounds={actualStrategyCompounds(published)} />
    <span>{lastStop == null ? "—" : `L${lastStop}`}</span>
  </button>;
}

function qualifyingDelta(value: number | null | undefined): string {
  return value == null ? "—" : `${value < 0 ? "" : "+"}${value.toFixed(3)}`;
}

function QualifyingRow({ driver, intelligence, timing, sectorTimingAvailable, showQStatus, onSelect }: { driver: Driver; intelligence?: QualifyingIntelligence; timing: boolean; sectorTimingAvailable: boolean; showQStatus: boolean; onSelect?: (driverNumber: string) => void }) {
  const model = intelligence?.drivers[driver.number];
  const latest = model?.scopeLatestLap;
  const lifecycle = driverLifecycle(driver);
  const status = lifecycle.label ?? (lifecycle.circulating ? "ON TRACK" : driver.activity === "IN_PIT" ? "IN PIT" : driver.activity === "ON_TRACK" ? "ON TRACK" : "—");
  const boundary = intelligence?.cutLine.status === "AVAILABLE"
    && ["Q1", "Q2", "SQ1", "SQ2"].includes(intelligence.phase)
    && intelligence.cutLine.advancePosition === driver.position;
  const delta = model?.benchmarkDelta === 0 && intelligence?.benchmark?.driverNumber === driver.number ? "LEADER" : qualifyingDelta(model?.benchmarkDelta);
  const results = model?.segmentResults ?? driver.qualifying_results ?? [null, null, null];
  return <button type="button" className={`timing-row timing-qualifying${timing ? " timing-qualifying-timing" : ""}${showQStatus ? " timing-qualifying-final" : ""}${timing && sectorTimingAvailable ? " timing-qualifying-sectors" : ""} ${lifecycleClassName(driver)}${boundary ? " timing-cut-boundary" : ""}`} role="row" data-driver-number={driver.number} onClick={() => onSelect?.(driver.number)}>
    <strong>{driver.position ?? "—"}</strong><span className="qualifying-driver-identity"><DriverIdentity driver={driver} secondaryLabel={model?.qStatus?.startsWith("OUT ") ? `${model.qStatus} · ${driver.team ?? "—"}` : undefined} /></span>
    {timing ? <>
      <DataValue compact value={model?.scopeBest ?? "—"} />
      {sectorTimingAvailable && <DataValue compact value={formatSector(latest?.sector1 ?? null) ?? "—"} />}
      {sectorTimingAvailable && <DataValue compact value={formatSector(latest?.sector2 ?? null) ?? "—"} />}
      {sectorTimingAvailable && <DataValue compact value={formatSector(latest?.sector3 ?? null) ?? "—"} />}
    </> : results.map((value, index) => <DataValue key={index} compact value={formatLapTime(value)} />)}
    <DataValue compact value={delta} />
    <DataValue compact value={qualifyingDelta(model?.intervalToAhead)} />
    <CompoundBadge compound={driver.compound} compact />
    {!timing && <span>{driver.tyre_age == null ? "—" : `${driver.tyre_age}L`}</span>}
    <span className="qualifying-driver-status">{status}</span>
    {showQStatus && <strong className="qualifying-status">{model?.qStatus ?? "—"}</strong>}
  </button>;
}

function PracticeRow({ driver, onSelect }: { driver: Driver; onSelect?: (driverNumber: string) => void }) {
  const lifecycle = driverLifecycle(driver);
  return <button type="button" className={"timing-row timing-practice " + lifecycleClassName(driver)} role="row" data-driver-number={driver.number} onClick={() => onSelect?.(driver.number)}>
    <strong>{driver.position ?? "—"}</strong><DriverIdentity driver={driver} />
    <CompoundBadge compound={driver.compound} compact />
    <DataValue compact value={driver.tyre_age} availability={driver.availability.tyre_age} />
    <DataValue compact value={driver.last_lap} availability={driver.availability.last_lap} />
    <DataValue compact value={driver.best_lap} availability={driver.availability.best_lap} />
    <DataValue compact value={driver.best_lap_delta_to_leader} availability={driver.availability.best_lap_delta_to_leader} />
    <DataValue compact value={driver.best_lap_delta_to_ahead} availability={driver.availability.best_lap_delta_to_ahead} />
    <DataValue compact value={driver.stint_laps} availability={driver.availability.stint_laps} />
    <span>{driver.pit_count}</span>
    <span className="practice-driver-status">{lifecycle.label}</span>
  </button>;
}

const headers = {
  practice: ["P", "DRIVER", "TYRE", "AGE", "LAST", "BEST", "GAP", "INT", "STINT", "PIT", "STATUS"],
};

const raceModeHeaders = {
  standard: ["P", "DRIVER / TEAM", "GAP", "TYRE", "AGE", "LAST", "PIT"],
  timing: ["P", "DRIVER / TEAM", "GAP", "TYRE", "S1", "S2", "S3", "LAST", "BEST"],
  strategy: ["P", "DRIVER / TEAM", "GAP", "TYRE", "AGE", "STINT", "PIT"],
};

export function TimingTower({ drivers, variant, mode = "standard", analytics, replayAvailable, sectorTimingAvailable = false, intervalsAvailable = false, desktopRaceColumns = false, compact = false, tvScale, toolbar, onSelectDriver }: TimingTowerProps) {
  const tableRef = useRef<HTMLDivElement>(null);
  useTowerMotion(tableRef, drivers, analytics?.story);
  const tableId = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const [tableSize, setTableSize] = useState({ width: 0, height: 0, header: 26 });
  const [showAll, setShowAll] = useState(false);
  useEffect(() => {
    const table = tableRef.current;
    if (!table) return;
    const header = table.querySelector<HTMLElement>(".timing-header");
    const measure = () => {
      const bounds = table.getBoundingClientRect();
      const next = { width: bounds.width, height: table.clientHeight, header: header?.getBoundingClientRect().height ?? 26 };
      setTableSize((current) => current.width === next.width && current.height === next.height && current.header === next.header ? current : next);
    };
    const observer = new ResizeObserver(measure);
    observer.observe(table);
    if (header) observer.observe(header);
    return () => observer.disconnect();
  }, []);
  // The approved desktop extension is opt-in; mobile and TV retain their inventories.
  const showInterval = (variant === "race" && mode === "timing" && intervalsAvailable)
    || (variant === "race" && desktopRaceColumns && intervalsAvailable);
  const qualifyingTiming = variant === "qualifying" && mode === "timing";
  const qualifyingPhase = analytics?.qualifying?.phase;
  const qualifyingBestHeader = qualifyingPhase && qualifyingPhase !== "UNKNOWN" ? qualifyingPhase : "BEST";
  const qualifyingFinal = variant === "qualifying" && analytics?.qualifying.final === true;
  const qualifyingSegments = analytics?.sessionKind === "sprint_qualifying" ? ["SQ1", "SQ2", "SQ3"] : ["Q1", "Q2", "Q3"];
  const raceHeaders = compact && mode === "standard" ? ["P", "DRIVER / TEAM", "GAP", "TYRE", "PIT"] : mode === "strategy"
    ? [...raceModeHeaders.strategy, "TYRE STRATEGY", "LAST STOP"] : raceModeHeaders[mode];
  const headersForView = variant === "race"
    ? showInterval ? [...raceHeaders.slice(0, 3), "INT", ...raceHeaders.slice(3)] : raceHeaders
    : variant === "qualifying"
      ? ["P", "DRIVER / TEAM", ...(qualifyingTiming
        ? [qualifyingBestHeader, ...(sectorTimingAvailable ? ["S1", "S2", "S3"] : []), "GAP", "INT", "TYRE", "STATUS"]
        : [...qualifyingSegments, "GAP", "INT", "TYRE", "AGE", "STATUS"]), ...(qualifyingFinal ? ["Q STATUS"] : [])]
      : headers.practice;
  const fit = fitTowerColumns(headersForView, tableSize.width, showAll, tvScale == null ? 1 : Math.max(.7, tvScale * 1.45));
  const rowHeight = fittedTowerRowHeight(tableSize.height, tableSize.header, drivers.length, tvScale != null);
  const rowStyle = { "--tower-columns": fit.template, "--tower-minimum": `${fit.minimumWidth}px`, "--tower-row-height": `${rowHeight}px` } as CSSProperties;
  const rowClass = variant === "race" && mode !== "standard" ? `race-${mode}` : variant;
  const qualifying = analytics?.qualifying;
  const raceLeader = drivers.find((driver) => driver.position === 1);
  const qualifierTitle = qualifying?.settlement === "SETTLING" ? `${qualifying.phase} FLAG · LAPS FINISHING` : qualifying?.settlement === "SOURCE_COMPLETE" ? "QUALIFYING · PROVISIONAL" : qualifying?.phase && qualifying.phase !== "UNKNOWN" ? `QUALIFYING · ${qualifying.phase}${qualifyingFinal ? " FLAG" : ""}` : "QUALIFYING";
  return <Panel eyebrow={variant === "race" ? "CLASSIFICATION" : variant === "qualifying" ? qualifierTitle : "RUN CLASSIFICATION"} title="Timing tower" action={<div className="panel-actions">{variant === "qualifying" && qualifying?.sessionClock && <strong className="qualifying-clock">{qualifying.sessionClock} REMAINING</strong>}<span className="panel-badge">{drivers.length} DRIVERS</span>{fit.hidden.length > 0 && <button className="tower-hidden-columns" title={`Hidden columns: ${fit.hidden.map((index) => headersForView[index]).join(", ")}. Show all in a scrolling table.`} onClick={() => setShowAll(true)}>+{fit.hidden.length} HIDDEN</button>}{showAll && <button className="tower-hidden-columns" onClick={() => setShowAll(false)}>FIT</button>}{toolbar}</div>} className="timing-panel">
    {!replayAvailable && <div className="panel-empty">TIMING DATA NOT AVAILABLE FOR THIS SESSION</div>}
    {replayAvailable && drivers.length === 0 && <div className="panel-empty">NO TIMING ROWS YET</div>}
    <div ref={tableRef} id={tableId} style={rowStyle} className={`timing-table adaptive-timing timing-${rowClass}`} role="table" aria-label={variant === "qualifying" ? `Qualifying ${qualifyingTiming ? "Timing" : "Standard"}` : undefined}>
      {fit.hidden.length > 0 && <style>{fit.hidden.map((index) => `#${tableId} > :is(.timing-header, .timing-row) > :nth-child(${index + 1}) { display: none; }`).join("\n")}</style>}
      <div className={`timing-header timing-${rowClass}${showInterval ? " timing-with-interval" : ""}${variant === "qualifying" && qualifyingFinal ? " timing-qualifying-final" : ""}${variant === "race" && mode === "strategy" ? " timing-race-strategy-detail" : ""}${qualifyingTiming ? " timing-qualifying-timing" : ""}${qualifyingTiming && sectorTimingAvailable ? " timing-qualifying-sectors" : ""}`} role="row">{headersForView.map((header) => <span key={header} className={header === "INT" || (["practice", "qualifying"].includes(variant) && header === "GAP") || (variant === "qualifying" && ["S1", "S2", "S3"].includes(header)) ? "timing-header-help" : undefined} title={variant === "qualifying" && header === "GAP" ? "Best-lap gap to the fastest driver in this scope (active segment when known)." : variant === "qualifying" && header === "INT" ? "Best-lap difference to the driver immediately above, within the same scope." : variant === "qualifying" && ["S1", "S2", "S3"].includes(header) ? "Sector from the latest completed lap in this scope; may differ from the best lap." : header === "INT" ? variant === "practice" ? "Best-lap difference to the driver above." : "Interval to the driver immediately above in the classification." : variant === "practice" && header === "GAP" ? "Best-lap gap to the leader (P1)." : variant === "race" && header === "GAP" ? "Gap to the leader or driver status." : undefined}>{header}</span>)}</div>
      {drivers.map((driver) => variant === "race" && mode === "timing"
        ? <RaceTimingRow driver={driver} leader={raceLeader} intervalsAvailable={showInterval} onSelect={onSelectDriver} key={driver.number} />
        : variant === "race" && mode === "strategy"
          ? <RaceStrategyRow driver={driver} leader={raceLeader} intervalsAvailable={showInterval} analytics={analytics} onSelect={onSelectDriver} key={driver.number} />
          : variant === "race"
            ? <RaceRow compact={compact} driver={driver} leader={raceLeader} intervalsAvailable={showInterval} onSelect={onSelectDriver} key={driver.number} />
            : variant === "qualifying"
               ? <QualifyingRow driver={driver} intelligence={qualifying} timing={qualifyingTiming} sectorTimingAvailable={sectorTimingAvailable} showQStatus={qualifyingFinal} onSelect={onSelectDriver} key={driver.number} />
              : <PracticeRow driver={driver} onSelect={onSelectDriver} key={driver.number} />)}
    </div>
  </Panel>;
}
