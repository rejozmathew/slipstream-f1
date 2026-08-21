import type { ReactNode } from "react";

import type { AnalyticsMetric, AnalyticsSnapshot } from "../../domain/protocol";
import { CompoundBadge, StrategyCompoundTransition } from "../shared/CompoundBadge";
import { InfoPopover } from "../shared/InfoPopover";
import { Panel } from "../shared/Panel";

type StrategyOutlookProps = {
  analytics?: AnalyticsSnapshot | null;
  driverNumber?: string | null;
  compact?: boolean;
  action?: ReactNode;
};

const meanings: Record<string, string> = {
  PRIMARY: "The most supported compound sequence for this scope at the current replay time.",
  ALTERNATE: "A secondary compound sequence with enough independent evidence to show.",
  "PIT WINDOW": "The future lap range projected from comparable stint life and the current stint start.",
  NEXT: "The next compound supported by comparable race-like transitions.",
  DEGRADATION: "Representative clean-lap pace change per lap.",
  "PIT-LANE DURATION": "Comparable race-like pit-lane time observed in the current meeting (raw observed lane time, not net loss).",
  "TYRE STRESS": "A categorical reading of clean-lap degradation evidence.",
};

function metricText(item: AnalyticsMetric | undefined) {
  if (!item || item.value == null) return "—";
  if (Array.isArray(item.value)) return `L${item.value[0]}–${item.value[1]}`;
  const suffix = item.unit === "s" ? "s" : item.unit === "s/lap" ? " s/lap" : "";
  return `${item.value}${suffix}`;
}

function metricQuality(item?: AnalyticsMetric) {
  if (!item || item.status === "UNKNOWN") return "UNKNOWN · INSUFFICIENT EVIDENCE";
  if (!item.quality || item.quality === "observed") return item.status;
  return `${item.status} · ${item.quality.toUpperCase()} EVIDENCE`;
}

function StrategyMetric({ label, item, display = "text" }: { label: string; item?: AnalyticsMetric; display?: "text" | "compound" | "transition" }) {
  const evidence = item?.evidenceBasis.length ? item.evidenceBasis.join(" · ") : "No supporting evidence is available.";
  let value: ReactNode = metricText(item);
  if (display === "compound") value = <CompoundBadge compound={typeof item?.value === "string" ? item.value : null} compact />;
  if (display === "transition") value = <StrategyCompoundTransition value={typeof item?.value === "string" ? item.value : null} compact />;
  return <div className="strategy-metric">
    <span>{label}<InfoPopover meaning={meanings[label] ?? "A source-neutral strategy metric."} why={evidence} /></span>
    <strong>{value}</strong>
    <small>{metricQuality(item)}</small>
  </div>;
}

export function StrategyOutlook({ analytics, driverNumber, compact = false, action }: StrategyOutlookProps) {
  const selectedDriver = driverNumber ? analytics?.drivers[driverNumber] : null;
  const strategy = selectedDriver?.strategy ?? (!driverNumber ? analytics?.raceStrategy : null);
  const contextStatus = analytics?.context.status ?? "unavailable";
  const stage = analytics?.stage ?? "BASELINE_AVAILABLE";
  const scopeLabel = selectedDriver ? `CAR ${selectedDriver.driverNumber}` : strategy?.scope === "RACE" ? "RACE WIDE" : "NO EVIDENCE";
  return <Panel eyebrow="STRATEGY" title="Strategy Outlook" className={`strategy-panel${compact ? " strategy-panel-compact" : ""}`} action={action ?? <span className={`panel-badge context-${contextStatus}`}>WEEKEND CONTEXT · {contextStatus.toUpperCase()}</span>}>
    <div className="strategy-content">
      <div className="strategy-stage"><span>{stage.replaceAll("_", " ")}</span><strong>{scopeLabel}</strong></div>
      {strategy?.changes?.map((change) => <div className="strategy-change" key={change}>{change}</div>)}
      {!strategy && <div className="strategy-unavailable" role="status"><strong>—</strong><p>Strategy remains unavailable until normalized evidence supports this scope.</p></div>}
      {strategy && <><div className="strategy-grid">
        <StrategyMetric label="PRIMARY" item={strategy.primaryStrategy} display="transition" />
        <StrategyMetric label="ALTERNATE" item={strategy.alternateStrategy} display="transition" />
        <StrategyMetric label="PIT WINDOW" item={strategy.pitWindow} />
        <StrategyMetric label="NEXT" item={strategy.likelyNextCompound} display="compound" />
        <StrategyMetric label="DEGRADATION" item={strategy.degradation} />
        <StrategyMetric label="PIT-LANE DURATION" item={strategy.pitLoss} />
        {!compact && <StrategyMetric label="TYRE STRESS" item={strategy.tyreStress} />}
      </div><p className="strategy-rules-note">{strategy.rulesNote}</p></>}
    </div>
  </Panel>;
}
