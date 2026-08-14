import { formatSector } from "../../domain/format";
import type { Driver } from "../../domain/protocol";
import { DataValue } from "../shared/DataValue";

export function BattleDriverCard({ driver, side }: { driver: Driver | null; side: "left" | "right" }) {
  if (!driver) return <section className={`battle-driver battle-driver-${side}`}><div className="panel-empty">SELECT A DRIVER</div></section>;
  return <section className={`battle-driver battle-driver-${side}`} style={{ "--team": `#${driver.team_colour ?? "77808f"}` } as CSSProperties}>
    <header><span>P{driver.position ?? "-"}</span><div><strong>{driver.code ?? driver.number}</strong><small>{driver.name ?? "Driver"}</small></div><b>#{driver.number}</b></header>
    <p>{driver.team ?? "Team unavailable"}</p>
    <div className="battle-driver-metrics">
      <div><span>GAP TO LEADER</span><DataValue compact value={driver.position === 1 ? "LEADER" : driver.gap_to_leader} availability={driver.availability.gap_to_leader} /></div>
      <div><span>TYRE / AGE</span><strong>{driver.compound?.[0] ?? "-"} <i>{driver.tyre_age == null ? "-" : `${driver.tyre_age}L`}</i></strong></div>
      <div><span>LAST LAP</span><DataValue compact value={driver.last_lap} availability={driver.availability.last_lap} /></div>
      <div><span>BEST LAP</span><DataValue compact value={driver.best_lap} availability={driver.availability.best_lap} /></div>
    </div>
    <div className="battle-sectors"><span>S1 <DataValue compact value={formatSector(driver.sector_1)} availability={driver.availability.sector_1} /></span><span>S2 <DataValue compact value={formatSector(driver.sector_2)} availability={driver.availability.sector_2} /></span><span>S3 <DataValue compact value={formatSector(driver.sector_3)} availability={driver.availability.sector_3} /></span></div>
  </section>;
}
import type { CSSProperties } from "react";

