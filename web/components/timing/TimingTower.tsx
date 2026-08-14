import { formatSector } from "../../domain/format";
import type { Driver } from "../../domain/protocol";
import { DataValue } from "../shared/DataValue";
import { Panel } from "../shared/Panel";

export type TimingVariant = "race" | "qualifying" | "practice";

type TimingTowerProps = {
  drivers: Driver[];
  variant: TimingVariant;
  replayAvailable: boolean;
};

function compoundClass(compound: string | null) {
  return `compound compound-${(compound ?? "unknown").toLowerCase()}`;
}

function DriverIdentity({ driver }: { driver: Driver }) {
  return (
    <span className="driver-cell">
      <i style={{ backgroundColor: `#${driver.team_colour ?? "77808f"}` }} />
      <b>{driver.code ?? driver.number}</b>
      <span><small>{driver.name?.split(" ").slice(-1)[0] ?? "UNKNOWN"}</small><em>{driver.team ?? "TEAM UNKNOWN"}</em></span>
    </span>
  );
}

function RaceRow({ driver }: { driver: Driver }) {
  return (
    <div className="timing-row timing-race" role="row">
      <strong>{driver.position ?? "-"}</strong><DriverIdentity driver={driver} />
      <DataValue value={driver.position === 1 ? "-" : driver.interval_to_ahead} availability={driver.availability.interval_to_ahead} />
      <DataValue value={driver.position === 1 ? "LEADER" : driver.gap_to_leader} availability={driver.availability.gap_to_leader} />
      <i className={compoundClass(driver.compound)}>{driver.compound?.[0] ?? "?"}</i>
      <DataValue value={driver.tyre_age} availability={driver.availability.tyre_age} />
      <DataValue value={driver.last_lap ?? driver.best_lap} availability={driver.availability.last_lap} />
      <span>{driver.pit_count}</span>
    </div>
  );
}

function QualifyingRow({ driver }: { driver: Driver }) {
  return (
    <div className="timing-row timing-qualifying" role="row">
      <strong>{driver.position ?? "-"}</strong><DriverIdentity driver={driver} />
      <DataValue value={driver.status} />
      <DataValue value={formatSector(driver.sector_1)} availability={driver.availability.sector_1} />
      <DataValue value={formatSector(driver.sector_2)} availability={driver.availability.sector_2} />
      <DataValue value={formatSector(driver.sector_3)} availability={driver.availability.sector_3} />
      <DataValue value={driver.best_lap ?? driver.last_lap} availability={driver.availability.best_lap} />
      <i className={compoundClass(driver.compound)}>{driver.compound?.[0] ?? "?"}</i>
    </div>
  );
}

function PracticeRow({ driver }: { driver: Driver }) {
  return (
    <div className="timing-row timing-practice" role="row">
      <strong>{driver.position ?? "-"}</strong><DriverIdentity driver={driver} />
      <i className={compoundClass(driver.compound)}>{driver.compound?.[0] ?? "?"}</i>
      <DataValue value={driver.tyre_age} availability={driver.availability.tyre_age} />
      <DataValue value={driver.last_lap} availability={driver.availability.last_lap} />
      <DataValue value={driver.best_lap} availability={driver.availability.best_lap} />
      <DataValue value={driver.stint_laps} availability={driver.availability.stint_laps} />
      <span>{driver.pit_count}</span>
    </div>
  );
}

const headers = {
  race: ["P", "DRIVER", "INT", "GAP", "TYRE", "AGE", "LAST LAP", "PIT"],
  qualifying: ["P", "DRIVER", "STATE", "S1", "S2", "S3", "BEST", "TYRE"],
  practice: ["P", "DRIVER", "TYRE", "AGE", "LAST", "BEST", "STINT", "PIT"],
};

export function TimingTower({ drivers, variant, replayAvailable }: TimingTowerProps) {
  const Row = variant === "race" ? RaceRow : variant === "qualifying" ? QualifyingRow : PracticeRow;
  return (
    <Panel eyebrow={variant === "race" ? "CLASSIFICATION" : variant === "qualifying" ? "SESSION CLASSIFICATION" : "RUN CLASSIFICATION"} title="Timing tower" action={<span className="panel-badge">{drivers.length} DRIVERS</span>} className="timing-panel">
      {!replayAvailable && <div className="panel-empty">TIMING DATA - UNAVAILABLE</div>}
      {replayAvailable && drivers.length === 0 && <div className="panel-empty">TIMING DATA - UNKNOWN AT THIS SESSION TIME</div>}
      <div className={`timing-table timing-${variant}`} role="table">
        <div className={`timing-header timing-${variant}`} role="row">
          {headers[variant].map((header) => <span key={header}>{header}</span>)}
        </div>
        {drivers.map((driver) => <Row driver={driver} key={driver.number} />)}
      </div>
    </Panel>
  );
}