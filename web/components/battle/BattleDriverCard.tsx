import { formatSector } from "../../domain/format";
import { actualStrategyCompounds, dryTyreRequirementText } from "../../domain/pirelliPresentation.mjs";
import type { AnalyticsSnapshot, Driver } from "../../domain/protocol";
import { CompoundBadge, CompoundSequence } from "../shared/CompoundBadge";
import { DataValue } from "../shared/DataValue";
import { storyTeamStyle } from "../story/presentation";

export function BattleDriverCard({ driver, side, analytics }: { driver: Driver | null; side: "left" | "right"; analytics?: AnalyticsSnapshot | null }) {
  if (!driver) return <section className={`battle-driver battle-driver-${side}`}><div className="panel-empty">SELECT A DRIVER</div></section>;
  const published = analytics?.publishedStrategy?.drivers[driver.number];
  const completed = published?.actualStrategy?.completedStops ?? analytics?.drivers[driver.number]?.pitEvents.length;
  return <section className={`battle-driver battle-driver-${side} battle-driver-compact`} style={storyTeamStyle(driver)}>
    <header><div><span>P{driver.position ?? "—"}</span><strong>{driver.code ?? driver.number}<small>{driver.name ?? "Driver"} · #{driver.number}</small></strong></div><em>{driver.team ?? "Team unavailable"}</em></header>
    <div className="battle-driver-metrics">
      <div><span>GAP TO LEADER</span><DataValue compact value={driver.position === 1 ? "LEADER" : driver.gap_to_leader} availability={driver.availability.gap_to_leader} /></div>
      <div><span>TYRE / AGE</span><strong><CompoundBadge compound={driver.compound} compact /> <i>{driver.tyre_age == null ? "—" : `${driver.tyre_age}L`}</i></strong></div>
      <div><span>LAST LAP</span><DataValue compact value={driver.last_lap} availability={driver.availability.last_lap} /></div>
      <div><span>BEST LAP</span><DataValue compact value={driver.best_lap} availability={driver.availability.best_lap} /></div>
      <div><span>S1 · S2 · S3</span><strong className="battle-card-sectors">{[driver.sector_1, driver.sector_2, driver.sector_3].map(value => formatSector(value) ?? "—").join(" · ")}</strong></div>
      <div><span>STOPS</span><strong>{completed ?? "—"}</strong></div>
      <div><span>ACTUAL TYRE STRATEGY</span><CompoundSequence compounds={actualStrategyCompounds(published)} /></div>
      <div><span>DRY RULE</span><strong className="battle-card-rule">{dryTyreRequirementText(published) ?? "—"}</strong></div>
    </div>
  </section>;
}

