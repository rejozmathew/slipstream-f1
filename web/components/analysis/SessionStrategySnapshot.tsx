import type { AnalyticsSnapshot } from "../../domain/protocol";
import { NO_SPECIFIC_PIRELLI_STRATEGY, prioritizedPirelliContextFacts } from "../../domain/pirelliPresentation.mjs";
import { PirelliNomination, PublishedOptionCard } from "./PublishedStrategy";
import { Panel } from "../shared/Panel";

type SessionStrategySnapshotProps = {
  analytics: AnalyticsSnapshot | null;
  onOpenStrategy: () => void;
  compact?: boolean;
};

export function SessionStrategySnapshot({ analytics, onOpenStrategy, compact = false }: SessionStrategySnapshotProps) {
  const intelligence = analytics?.publishedStrategy;
  const baseline = intelligence?.baseline;
  const contextFact = prioritizedPirelliContextFacts(baseline?.contextFacts ?? [], 1)[0];
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
  const visibleOptions = baseline?.options.slice(0, compact ? 1 : 2) ?? [];
  const hiddenOptionCount = Math.max((baseline?.options.length ?? 0) - visibleOptions.length, 0);
  const pirelliContent = baseline?.status === "PRESENT"
    ? <>{baseline.options.length
      ? <><div className="session-published-options">{visibleOptions.map((option) => <PublishedOptionCard key={option.id} option={option} compact />)}</div>{hiddenOptionCount > 0 && <small className="session-pirelli-more">+{hiddenOptionCount} MORE PIRELLI {hiddenOptionCount === 1 ? "STRATEGY" : "STRATEGIES"}</small>}</>
      : <div className="session-pirelli-context-only"><strong>{NO_SPECIFIC_PIRELLI_STRATEGY}</strong>{contextFact && <p><span>{contextFact.category.replaceAll("_", " ")}</span>{contextFact.statement}</p>}</div>}<PirelliNomination baseline={baseline} /></>
    : <p>{baseline?.status === "FETCHING" ? "Loading official Pirelli tyre strategy… Current race facts remain available." : baseline?.status === "RETRYING" ? "Official Pirelli strategy retry scheduled. Current race facts remain available." : "No official Pirelli tyre strategy is available for this session. Current race facts remain available."}</p>;
  return <Panel eyebrow="STRATEGY CONTEXT" title="Pirelli tyre strategy · Race now" className={`session-strategy-read${compact ? " session-strategy-read-compact" : ""}`} action={<button type="button" className="panel-action-button" onClick={onOpenStrategy}>VIEW STRATEGY →</button>}>
    <div className="session-strategy-zones">
      <section><header><span>{baseline?.status === "PRESENT" && baseline.options.length ? "PIRELLI TYRE STRATEGIES" : "PIRELLI TYRE STRATEGY"}</span>{baseline?.status === "PRESENT" && <b>PUBLISHED</b>}</header>{pirelliContent}</section>
      <section><header><span>RACE NOW</span><b>{read?.raceLifecycle ?? "—"}</b></header>{read ? <div className="session-race-now"><strong>{population}</strong><small>{Object.entries(read.completedStopDistribution).map(([stops, count]) => `${stops} stops: ${count}`).join(" · ") || "NO COMPLETED STOPS"}</small></div> : <p>Race Read is not available yet.</p>}</section>
      <section><header><span>NOW</span><b>FACTUAL</b></header><p>{read?.summaryFacts[0] ?? "No unusual current-race fact is established yet."}</p></section>
    </div>
  </Panel>;
}
