import type { ReactNode } from "react";

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

function RaceRow({ driver, leader, intervalsAvailable, onSelect }: { driver: Driver; leader?: Driver; intervalsAvailable: boolean; onSelect?: (driverNumber: string) => void }) {
  const lifecycle = driverLifecycle(driver);
  return <button type="button" className={`timing-row timing-race${intervalsAvailable ? " timing-with-interval" : ""} ${lifecycleClassName(driver)}`} role="row" onClick={() => onSelect?.(driver.number)}>
    <RaceCore driver={driver} leader={leader} intervalsAvailable={intervalsAvailable} />
    <DataValue compact value={driver.tyre_age} availability={driver.availability.tyre_age} />
    {lifecycle.terminal ? <span>—</span> : <DataValue compact value={driver.last_lap ?? driver.best_lap} availability={driver.availability.last_lap} />}
    <span>{driver.pit_count}</span>
  </button>;
}

function RaceTimingRow({ driver, leader, intervalsAvailable, onSelect }: { driver: Driver; leader?: Driver; intervalsAvailable: boolean; onSelect?: (driverNumber: string) => void }) {
  return <button type="button" className={`timing-row timing-race-timing${intervalsAvailable ? " timing-with-interval" : ""} ${lifecycleClassName(driver)}`} role="row" onClick={() => onSelect?.(driver.number)}>
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
  return <button type="button" className={`timing-row timing-race-strategy timing-race-strategy-detail${intervalsAvailable ? " timing-with-interval" : ""} ${lifecycleClassName(driver)}`} role="row" onClick={() => onSelect?.(driver.number)}>
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
  return <button type="button" className={`timing-row timing-qualifying${timing ? " timing-qualifying-timing" : ""}${showQStatus ? " timing-qualifying-final" : ""}${timing && sectorTimingAvailable ? " timing-qualifying-sectors" : ""} ${lifecycleClassName(driver)}${boundary ? " timing-cut-boundary" : ""}`} role="row" onClick={() => onSelect?.(driver.number)}>
    <strong>{driver.position ?? "—"}</strong><span className="qualifying-driver-identity"><DriverIdentity driver={driver} />{model?.qStatus?.startsWith("OUT ") && <small>{model.qStatus}</small>}</span>
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
  return <button type="button" className={"timing-row timing-practice " + lifecycleClassName(driver)} role="row" onClick={() => onSelect?.(driver.number)}>
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
  practice: ["P", "DRIVER", "TYRE", "AGE", "LAST", "BEST", "GAP", "INT", "STINT", "STOPS", "STATUS"],
};

const raceModeHeaders = {
  standard: ["P", "DRIVER / TEAM", "GAP", "TYRE", "AGE", "LAST", "PIT"],
  timing: ["P", "DRIVER / TEAM", "GAP", "TYRE", "S1", "S2", "S3", "LAST", "BEST"],
  strategy: ["P", "DRIVER / TEAM", "GAP", "TYRE", "AGE", "STINT", "PIT"],
};

export function TimingTower({ drivers, variant, mode = "standard", analytics, replayAvailable, sectorTimingAvailable = false, intervalsAvailable = false, desktopRaceColumns = false, toolbar, onSelectDriver }: TimingTowerProps) {
  // The approved desktop extension is opt-in; mobile and TV retain their inventories.
  const showInterval = (variant === "race" && mode === "timing" && intervalsAvailable)
    || (variant === "race" && desktopRaceColumns && intervalsAvailable);
  const qualifyingTiming = variant === "qualifying" && mode === "timing";
  const qualifyingPhase = analytics?.qualifying?.phase;
  const qualifyingBestHeader = qualifyingPhase && qualifyingPhase !== "UNKNOWN" ? qualifyingPhase : "BEST";
  const qualifyingFinal = variant === "qualifying" && analytics?.qualifying.final === true;
  const qualifyingSegments = analytics?.sessionKind === "sprint_qualifying" ? ["SQ1", "SQ2", "SQ3"] : ["Q1", "Q2", "Q3"];
  const raceHeaders = mode === "strategy"
    ? [...raceModeHeaders.strategy, "TYRE STRATEGY", "LAST STOP"] : raceModeHeaders[mode];
  const headersForView = variant === "race"
    ? showInterval ? [...raceHeaders.slice(0, 3), "INT", ...raceHeaders.slice(3)] : raceHeaders
    : variant === "qualifying"
      ? ["P", "DRIVER / TEAM", ...(qualifyingTiming
        ? [qualifyingBestHeader, ...(sectorTimingAvailable ? ["S1", "S2", "S3"] : []), "GAP", "INT", "TYRE", "STATUS"]
        : [...qualifyingSegments, "GAP", "INT", "TYRE", "AGE", "STATUS"]), ...(qualifyingFinal ? ["Q STATUS"] : [])]
      : headers.practice;
  const rowClass = variant === "race" && mode !== "standard" ? `race-${mode}` : variant;
  const qualifying = analytics?.qualifying;
  const raceLeader = drivers.find((driver) => driver.position === 1);
  const qualifierTitle = qualifyingFinal ? "QUALIFYING FINAL" : qualifying?.phase && qualifying.phase !== "UNKNOWN" ? `QUALIFYING · ${qualifying.phase}` : "QUALIFYING";
  return <Panel eyebrow={variant === "race" ? "CLASSIFICATION" : variant === "qualifying" ? qualifierTitle : "RUN CLASSIFICATION"} title="Timing tower" action={<div className="panel-actions">{variant === "qualifying" && qualifying?.sessionClock && <strong className="qualifying-clock">{qualifying.sessionClock} REMAINING</strong>}<span className="panel-badge">{drivers.length} DRIVERS</span>{toolbar}</div>} className="timing-panel">
    {!replayAvailable && <div className="panel-empty">TIMING DATA NOT AVAILABLE FOR THIS SESSION</div>}
    {replayAvailable && drivers.length === 0 && <div className="panel-empty">NO TIMING ROWS YET</div>}
    <div className={`timing-table timing-${rowClass}`} role="table" aria-label={variant === "qualifying" ? `Qualifying ${qualifyingTiming ? "Timing" : "Standard"}` : undefined}>
      <div className={`timing-header timing-${rowClass}${showInterval ? " timing-with-interval" : ""}${variant === "qualifying" && qualifyingFinal ? " timing-qualifying-final" : ""}${variant === "race" && mode === "strategy" ? " timing-race-strategy-detail" : ""}${qualifyingTiming ? " timing-qualifying-timing" : ""}${qualifyingTiming && sectorTimingAvailable ? " timing-qualifying-sectors" : ""}`} role="row">{headersForView.map((header) => <span key={header} className={header === "INT" || (["practice", "qualifying"].includes(variant) && header === "GAP") || (variant === "qualifying" && ["S1", "S2", "S3"].includes(header)) ? "timing-header-help" : undefined} title={variant === "qualifying" && header === "GAP" ? "Best-lap gap to the fastest driver in this scope (active segment when known)." : variant === "qualifying" && header === "INT" ? "Best-lap difference to the driver immediately above, within the same scope." : variant === "qualifying" && ["S1", "S2", "S3"].includes(header) ? "Sector from the latest completed lap in this scope; may differ from the best lap." : header === "INT" ? variant === "practice" ? "Best-lap difference to the driver above." : "Interval to the driver immediately above in the classification." : variant === "practice" && header === "GAP" ? "Best-lap gap to the leader (P1)." : variant === "race" && header === "GAP" ? "Gap to the leader or driver status." : undefined}>{header}</span>)}</div>
      {drivers.map((driver) => variant === "race" && mode === "timing"
        ? <RaceTimingRow driver={driver} leader={raceLeader} intervalsAvailable={showInterval} onSelect={onSelectDriver} key={driver.number} />
        : variant === "race" && mode === "strategy"
          ? <RaceStrategyRow driver={driver} leader={raceLeader} intervalsAvailable={showInterval} analytics={analytics} onSelect={onSelectDriver} key={driver.number} />
          : variant === "race"
            ? <RaceRow driver={driver} leader={raceLeader} intervalsAvailable={showInterval} onSelect={onSelectDriver} key={driver.number} />
            : variant === "qualifying"
               ? <QualifyingRow driver={driver} intelligence={qualifying} timing={qualifyingTiming} sectorTimingAvailable={sectorTimingAvailable} showQStatus={qualifyingFinal} onSelect={onSelectDriver} key={driver.number} />
              : <PracticeRow driver={driver} onSelect={onSelectDriver} key={driver.number} />)}
    </div>
  </Panel>;
}
