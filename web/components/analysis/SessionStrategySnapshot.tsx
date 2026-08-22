import type { AnalyticsSnapshot } from "../../domain/protocol";
import { Panel } from "../shared/Panel";

type SessionStrategySnapshotProps = {
  analytics: AnalyticsSnapshot | null;
  onOpenStrategy: () => void;
  compact?: boolean;
};

function distribution(value: Record<string, number> | undefined) {
  if (!value || Object.keys(value).length === 0) return "—";
  return Object.entries(value).map(([label, count]) => `${label} ${count}`).join(" · ");
}

export function SessionStrategySnapshot({ analytics, onOpenStrategy, compact = false }: SessionStrategySnapshotProps) {
  const read = analytics?.raceRead;
  const final = analytics?.strategyLifecycle === "FINAL";
  return <Panel eyebrow="RACE READ" title="Race strategy snapshot" className={`session-strategy-read${compact ? " session-strategy-read-compact" : ""}`} action={<button type="button" className="panel-action-button" onClick={onOpenStrategy}>VIEW STRATEGY →</button>}>
    {!read && <div className="strategy-unavailable" role="status"><strong>—</strong><p>Race Read is unavailable until normalized race evidence reaches this cursor.</p></div>}
    {read && <div className="session-read-grid">
      <div><span>FIELD SHAPE</span><strong>{read.strategyArchetype.value ?? "NOT ESTABLISHED"}</strong><small>{read.population.active} active · {read.population.terminal} terminal</small></div>
      <div><span>CURRENT TYRES</span><strong>{distribution(read.currentTyreDistribution)}</strong><small>{distribution(read.completedStopDistribution)} stops</small></div>
      <div><span>CONSTRAINTS</span><strong>{read.dryRequirementLandscape.unsatisfied > 0 ? `${read.dryRequirementLandscape.unsatisfied} REQUIRE DRY SPEC` : read.dryRequirementLandscape.unknown > 0 ? `${read.dryRequirementLandscape.unknown} RULE UNKNOWN` : "FIELD SATISFIED"}</strong><small>{final ? "RETROSPECTIVE · SESSION FINAL" : analytics?.projectionGate?.publishAllowed ? "OUTLOOK EARNED" : "OUTLOOK WITHHELD"}</small></div>
      {!compact && <div className="session-read-summary"><span>RACE READ</span><strong>{read.summaryFacts[0] ?? "No unusual field fact is established yet."}</strong></div>}
    </div>}
  </Panel>;
}
