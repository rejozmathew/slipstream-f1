import type { AnalyticsMetric, AnalyticsSnapshot } from "../../domain/protocol";
import { Panel } from "../shared/Panel";

type StrategyOutlookProps = {
  analytics?: AnalyticsSnapshot | null;
  driverNumber?: string | null;
  compact?: boolean;
};

function metricValue(item: AnalyticsMetric | undefined) {
  if (!item || item.value == null) return "—";
  if (Array.isArray(item.value)) return `L${item.value[0]}–${item.value[1]}`;
  const suffix = item.unit === "s" ? "s" : item.unit === "s/lap" ? " s/lap" : "";
  return `${item.value}${suffix}`;
}

function StrategyMetric({ label, item }: { label: string; item?: AnalyticsMetric }) {
  const evidence = item?.evidenceBasis.join(" · ") ?? "No supporting evidence is available.";
  return <div className="strategy-metric" title={`${item?.status ?? "UNKNOWN"} · ${evidence}`}>
    <span>{label}<i aria-label="Metric explanation">ⓘ</i></span>
    <strong>{metricValue(item)}</strong>
    <small>{item?.status ?? "UNKNOWN"}{item?.quality ? ` · ${item.quality.toUpperCase()}` : ""}</small>
  </div>;
}

export function StrategyOutlook({ analytics, driverNumber, compact = false }: StrategyOutlookProps) {
  const selected = driverNumber ? analytics?.drivers[driverNumber] : Object.values(analytics?.drivers ?? {})[0];
  const strategy = selected?.strategy;
  const contextStatus = analytics?.context.status ?? "unavailable";
  const stage = analytics?.stage ?? "BASELINE_AVAILABLE";
  return <Panel
    eyebrow="STRATEGY"
    title="Strategy Outlook"
    className={`strategy-panel${compact ? " strategy-panel-compact" : ""}`}
    action={<span className={`panel-badge context-${contextStatus}`}>WEEKEND CONTEXT · {contextStatus.toUpperCase()}</span>}
  >
    <div className="strategy-stage"><span>{stage.replaceAll("_", " ")}</span><strong>{selected ? `CAR ${selected.driverNumber}` : "NO DRIVER EVIDENCE"}</strong></div>
    {strategy?.changes?.map((change) => <div className="strategy-change" key={change}>{change}</div>)}
    {!selected && <div className="strategy-unavailable" role="status"><strong>—</strong><p>Strategy remains available only when normalized driver evidence exists.</p></div>}
    {selected && <>
      <div className="strategy-grid">
        <StrategyMetric label="PRIMARY" item={strategy?.primaryStrategy} />
        <StrategyMetric label="ALTERNATE" item={strategy?.alternateStrategy} />
        <StrategyMetric label="PIT WINDOW" item={strategy?.pitWindow} />
        <StrategyMetric label="NEXT" item={strategy?.likelyNextCompound} />
        <StrategyMetric label="DEGRADATION" item={strategy?.degradation} />
        <StrategyMetric label="PIT LOSS" item={strategy?.pitLoss} />
        {!compact && <StrategyMetric label="TYRE STRESS" item={strategy?.tyreStress} />}
        {!compact && <StrategyMetric label="REJOIN" item={strategy?.projectedRejoinPosition} />}
      </div>
      <p className="strategy-rules-note">{strategy?.rulesNote}</p>
    </>}
  </Panel>;
}
