import type { AnalyticsSnapshot } from "../../domain/protocol";
import { PublishedOptionCard } from "./PublishedStrategy";
import { Panel } from "../shared/Panel";

type SessionStrategySnapshotProps = {
  analytics: AnalyticsSnapshot | null;
  onOpenStrategy: () => void;
  compact?: boolean;
};

export function SessionStrategySnapshot({ analytics, onOpenStrategy, compact = false }: SessionStrategySnapshotProps) {
  const intelligence = analytics?.publishedStrategy;
  const baseline = intelligence?.baseline;
  const read = analytics?.raceRead;
  return <Panel eyebrow="STRATEGY CONTEXT" title="Pirelli baseline · Race now" className={`session-strategy-read${compact ? " session-strategy-read-compact" : ""}`} action={<button type="button" className="panel-action-button" onClick={onOpenStrategy}>VIEW STRATEGY →</button>}>
    <div className="session-strategy-zones">
      <section><header><span>PIRELLI BASELINE</span><b>{baseline?.status ?? "ABSENT"}</b></header>{baseline?.status === "PRESENT" && baseline.options.length ? <div className="session-published-options">{baseline.options.slice(0, compact ? 1 : 2).map((option) => <PublishedOptionCard key={option.id} option={option} compact />)}</div> : <p>No replay-admissible published strategy is available. Current race facts remain usable.</p>}</section>
      <section><header><span>RACE NOW</span><b>{analytics?.strategyLifecycle ?? "UNAVAILABLE"}</b></header>{read ? <div className="session-race-now"><strong>{read.population.active} ACTIVE · {read.population.terminal} TERMINAL</strong><small>{Object.entries(read.completedStopDistribution).map(([stops, count]) => `${count}×${stops}-stop`).join(" · ") || "NO FIELD STOP SHAPE"}</small></div> : <p>Race Read is unavailable at this cursor.</p>}</section>
      <section><header><span>NOW</span><b>FACTUAL</b></header><p>{intelligence?.fieldFacts[0] ?? read?.summaryFacts[0] ?? "No unusual current-race fact is established yet."}</p></section>
    </div>
  </Panel>;
}
