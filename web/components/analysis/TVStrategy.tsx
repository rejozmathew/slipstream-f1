import type { AnalyticsSnapshot, RaceState } from "../../domain/protocol";
import { driverLifecycle } from "../../domain/lifecycle";
import { CompoundBadge, CompoundSequence } from "../shared/CompoundBadge";
import { PirelliBaseline } from "./PublishedStrategy";
import { StrategyPitBoard } from "./StrategyPitBoard";

export function TVStrategy({ state, analytics }: { state: RaceState; analytics: AnalyticsSnapshot | null }) {
  const read = analytics?.raceRead;
  const sequences = new Map<string, { count: number; compounds: Array<string | null> }>();
  for (const driver of Object.values(state.drivers)) {
    const lifecycle = driverLifecycle(driver);
    if (!lifecycle.circulating && !lifecycle.inPit) continue;
    const compounds = analytics?.publishedStrategy?.drivers[driver.number]?.actualStrategy.compounds;
    if (!compounds?.length) continue;
    const key = compounds.join(",");
    sequences.set(key, { count: (sequences.get(key)?.count ?? 0) + 1, compounds });
  }
  return <div className="ref-tv-strategy"><StrategyPitBoard state={state} analytics={analytics} posture="tv" /><div className="ref-strategy-context"><section><h3>DRY RULE</h3><b>{read ? `${read.dryRequirementLandscape.unsatisfied} drivers still need another dry compound` : "Not available"}</b>{!!read?.dryRequirementLandscape.unknown && <small>{read.dryRequirementLandscape.unknown} unknown · {read.dryRequirementLandscape.denominator} assessed</small>}</section><section><h3>COMPOUND SEQUENCES</h3><div className="ref-strategy-sequences">{[...sequences].map(([key, group]) => <span key={key}><b>{group.count}</b><CompoundSequence compounds={group.compounds} /></span>)}</div></section><section><h3>STINT CONTEXT · COMPLETED</h3><div className="ref-strategy-sequences">{read && Object.entries(read.stintContextByCompound).map(([compound, value]) => <span key={compound}><CompoundBadge compound={compound} compact /><b>{value.completedStints} · median {value.medianLife.toFixed(1)}L</b></span>)}</div></section><PirelliBaseline baseline={analytics?.publishedStrategy?.baseline} fieldFacts={analytics?.publishedStrategy?.fieldFacts} compact /></div></div>;
}
