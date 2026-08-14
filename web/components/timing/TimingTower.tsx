import type { ReactNode } from "react";

import { formatSector } from "../../domain/format";
import type { Driver } from "../../domain/protocol";
import { DataValue } from "../shared/DataValue";
import { Panel } from "../shared/Panel";

export type TimingVariant = "race" | "qualifying" | "practice";

type TimingTowerProps = {
  drivers: Driver[];
  variant: TimingVariant;
  replayAvailable: boolean;
  toolbar?: ReactNode;
  onSelectDriver?: (driverNumber: string) => void;
};

function compoundClass(compound: string | null) {
  return `compound compound-${(compound ?? "unknown").toLowerCase()}`;
}

function DriverIdentity({ driver }: { driver: Driver }) {
  return (
    <span className="driver-cell">
      <i style={{ backgroundColor: `#${driver.team_colour ?? "77808f"}` }} />
      <b>{driver.code ?? driver.number}</b>
      <span><small>{driver.name?.split(" ").slice(-1)[0] ?? "\u2014"}</small><em>{driver.team ?? "\u2014"}</em></span>
    </span>
  );
}

function RaceRow({ driver, onSelect }: { driver: Driver; onSelect?: (driverNumber: string) => void }) {
  return (
    <button type="button" className="timing-row timing-race" role="row" onClick={() => onSelect?.(driver.number)}>
      <strong>{driver.position ?? "-"}</strong><DriverIdentity driver={driver} />
      <DataValue compact value={driver.position === 1 ? "-" : driver.interval_to_ahead} availability={driver.availability.interval_to_ahead} />
      <DataValue compact value={driver.position === 1 ? "LEADER" : driver.gap_to_leader} availability={driver.availability.gap_to_leader} />
      <i className={compoundClass(driver.compound)}>{driver.compound?.[0] ?? "?"}</i>
      <DataValue compact value={driver.tyre_age} availability={driver.availability.tyre_age} />
      <DataValue compact value={driver.last_lap ?? driver.best_lap} availability={driver.availability.last_lap} />
      <span>{driver.pit_count}</span>
    </button>
  );
}

function QualifyingRow({ driver, onSelect }: { driver: Driver; onSelect?: (driverNumber: string) => void }) {
  return (
    <button type="button" className="timing-row timing-qualifying" role="row" onClick={() => onSelect?.(driver.number)}>
      <strong>{driver.position ?? "-"}</strong><DriverIdentity driver={driver} />
      <DataValue compact value={driver.status} />
      <DataValue compact value={formatSector(driver.sector_1)} availability={driver.availability.sector_1} />
      <DataValue compact value={formatSector(driver.sector_2)} availability={driver.availability.sector_2} />
      <DataValue compact value={formatSector(driver.sector_3)} availability={driver.availability.sector_3} />
      <DataValue compact value={driver.best_lap ?? driver.last_lap} availability={driver.availability.best_lap} />
      <i className={compoundClass(driver.compound)}>{driver.compound?.[0] ?? "?"}</i>
    </button>
  );
}

function PracticeRow({ driver, onSelect }: { driver: Driver; onSelect?: (driverNumber: string) => void }) {
  return (
    <button type="button" className="timing-row timing-practice" role="row" onClick={() => onSelect?.(driver.number)}>
      <strong>{driver.position ?? "-"}</strong><DriverIdentity driver={driver} />
      <i className={compoundClass(driver.compound)}>{driver.compound?.[0] ?? "?"}</i>
      <DataValue compact value={driver.tyre_age} availability={driver.availability.tyre_age} />
      <DataValue compact value={driver.last_lap} availability={driver.availability.last_lap} />
      <DataValue compact value={driver.best_lap} availability={driver.availability.best_lap} />
      <DataValue compact value={driver.stint_laps} availability={driver.availability.stint_laps} />
      <span>{driver.pit_count}</span>
    </button>
  );
}

const headers = {
  race: ["P", "DRIVER", "INT", "GAP", "TYRE", "AGE", "LAST LAP", "PIT"],
  qualifying: ["P", "DRIVER", "STATE", "S1", "S2", "S3", "BEST", "TYRE"],
  practice: ["P", "DRIVER", "TYRE", "AGE", "LAST", "BEST", "STINT", "PIT"],
};

export function TimingTower({ drivers, variant, replayAvailable, toolbar, onSelectDriver }: TimingTowerProps) {
  const Row = variant === "race" ? RaceRow : variant === "qualifying" ? QualifyingRow : PracticeRow;
  return (
    <Panel eyebrow={variant === "race" ? "CLASSIFICATION" : variant === "qualifying" ? "SESSION CLASSIFICATION" : "RUN CLASSIFICATION"} title="Timing tower" action={<div className="panel-actions"><span className="panel-badge">{drivers.length} DRIVERS</span>{toolbar}</div>} className="timing-panel">
      {!replayAvailable && <div className="panel-empty">TIMING DATA - UNAVAILABLE</div>}
      {replayAvailable && drivers.length === 0 && <div className="panel-empty">TIMING DATA - UNKNOWN AT THIS SESSION TIME</div>}
      <div className={`timing-table timing-${variant}`} role="table">
        <div className={`timing-header timing-${variant}`} role="row">
          {headers[variant].map((header) => <span key={header}>{header}</span>)}
        </div>
        {drivers.map((driver) => <Row driver={driver} onSelect={onSelectDriver} key={driver.number} />)}
      </div>
    </Panel>
  );
}
