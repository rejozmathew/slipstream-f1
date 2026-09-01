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
  const population = read ? [
    [read.population.running, "RUNNING"],
    [read.population.inPit, "IN PIT"],
    [read.population.stopped, "STOPPED"],
    [read.population.retired, "RETIRED / OUT"],
    [read.population.unconfirmed, "STATUS UNKNOWN"],
    [read.population.finished, "FINISHED"],
    [read.population.dnf, "DNF"],
    [read.population.dns, "DNS"],
    [read.population.dsq, "DSQ"],
  ].filter(([count]) => Number(count) > 0).map(([count, label]) => `${count} ${label}`).join(" · ") : "";
  return <Panel eyebrow="STRATEGY CONTEXT" title="Pirelli baseline · Race now" className={`session-strategy-read${compact ? " session-strategy-read-compact" : ""}`} action={<button type="button" className="panel-action-button" onClick={onOpenStrategy}>VIEW STRATEGY →</button>}>
    <div className="session-strategy-zones">
      <section><header><span>PIRELLI BASELINE</span>{baseline?.status === "PRESENT" && <b>PUBLISHED</b>}</header>{baseline?.status === "PRESENT" && baseline.options.length ? <div className="session-published-options">{baseline.options.slice(0, compact ? 1 : 2).map((option) => <PublishedOptionCard key={option.id} option={option} compact />)}</div> : <p>No applicable pre-race Pirelli strategy is published for this session. Current race facts remain usable.</p>}</section>
      <section><header><span>RACE NOW</span><b>{read?.raceLifecycle ?? "—"}</b></header>{read ? <div className="session-race-now"><strong>{population}</strong><small>{Object.entries(read.completedStopDistribution).map(([stops, count]) => `${stops} stops: ${count}`).join(" · ") || "NO COMPLETED STOPS"}</small></div> : <p>Race Read is not available yet.</p>}</section>
      <section><header><span>NOW</span><b>FACTUAL</b></header><p>{read?.summaryFacts[0] ?? "No unusual current-race fact is established yet."}</p></section>
    </div>
  </Panel>;
}
