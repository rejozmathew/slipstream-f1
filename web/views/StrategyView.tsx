import { useMemo } from "react";
import { Panel } from "../components/shared/Panel";
import { driverLifecycle, lifecycleClassName } from "../domain/lifecycle";
import { CompoundBadge } from "../components/shared/CompoundBadge";
import type { AnalyticsSnapshot, DryTyreRequirementState, RaceState } from "../domain/protocol";

type StrategyViewProps = {
  state: RaceState;
  analytics: AnalyticsSnapshot | null;
  onSelectDriver: (driverNumber: string) => void;
};

export function StrategyView({ state, analytics, onSelectDriver }: StrategyViewProps) {
  const drivers = useMemo(() => Object.values(state.drivers).sort((a, b) => (a.position ?? 999) - (b.position ?? 999)), [state.drivers]);

  // 1. Current Race Landscape
  const tyreDist = analytics?.startingTyreDistribution ?? {};
  const stopDist = analytics?.stopDistribution ?? {};
  const activeCount = analytics?.activeRunnerCount ?? 0;

  // 3. Rule / Constraint Landscape
  const dryRuleStates: Record<DryTyreRequirementState, number> = { SATISFIED: 0, UNSATISFIED: 0, NOT_APPLICABLE: 0, UNKNOWN: 0 };
  for (const d of drivers) {
    const st = analytics?.drivers[d.number]?.strategy?.dryTyreRequirement;
    if (st) {
      dryRuleStates[st] = (dryRuleStates[st] || 0) + 1;
    }
  }

  // Outlook
  const validity = analytics?.strategyValidity ?? "UNAVAILABLE";
  const strategyLifecycle = analytics?.strategyLifecycle ?? "UNAVAILABLE";

  return (
    <div className="strategy-view">
      <header className="experience-heading">
        <div>
          <span>RACE INTELLIGENCE</span>
          <h1>Strategy</h1>
          <p>Detailed field and race strategy lens.</p>
        </div>
        <div className="strategy-validity-state">
          <strong>OUTLOOK: {strategyLifecycle === "FINAL" ? "FINAL" : validity}</strong>
        </div>
      </header>
      
      <div className="strategy-grid">
        <Panel eyebrow="LANDSCAPE" title="Current Race Landscape">
           <div className="strategy-section">
             <span>ACTIVE RUNNERS</span>
             <strong>{activeCount}</strong>
           </div>
           <div className="strategy-section">
             <span>STARTING TYRES</span>
             <strong>{Object.entries(tyreDist).map(([c, n]) => `${c} ${n}`).join(" · ") || "—"}</strong>
           </div>
           <div className="strategy-section">
             <span>STOPS</span>
             <strong>{Object.entries(stopDist).map(([c, n]) => `${n} ${c}-stop`).join(" · ") || "—"}</strong>
           </div>
        </Panel>

        <Panel eyebrow="RULES" title="Rule / Constraint Landscape">
           <div className="strategy-section">
             <span>DRY TYRE REQUIREMENT</span>
             {dryRuleStates.UNSATISFIED > 0 && <strong className="unsatisfied">{dryRuleStates.UNSATISFIED} drivers still require another dry spec</strong>}
             {dryRuleStates.SATISFIED > 0 && <strong>{dryRuleStates.SATISFIED} drivers satisfied</strong>}
             {dryRuleStates.NOT_APPLICABLE > 0 && <strong>{dryRuleStates.NOT_APPLICABLE} not applicable</strong>}
           </div>
        </Panel>

        <Panel eyebrow="CONTEXT" title="Pre-Race / Historical Context">
           <div className="strategy-section">
             <span>OFFICIAL PRE-RACE CONTEXT</span>
             <strong>{analytics?.officialPreRace?.status === "PRESENT" ? `Available (${analytics.officialPreRace.source})` : "Absent"}</strong>
           </div>
           <div className="strategy-section">
             <span>HISTORICAL CONTEXT</span>
             <strong>{analytics?.historical?.status === "PRESENT" ? `${analytics.historical.season} Data Available` : "Absent"}</strong>
           </div>
        </Panel>
      </div>
      
      <Panel eyebrow="DRIVERS" title="Driver Strategy Landscape" className="driver-strategy-panel">
         <table className="driver-strategy-table">
            <thead>
               <tr>
                  <th>P</th>
                  <th>DRIVER</th>
                  <th>TYRE</th>
                  <th>AGE</th>
                  <th>STOPS</th>
                  <th>RULE</th>
                  <th>PACE</th>
                  <th>PLAN</th>
               </tr>
            </thead>
            <tbody>
               {drivers.map(d => {
                  const lifecycle = driverLifecycle(d);
                  const s = analytics?.drivers[d.number]?.strategy;
                  const disposition = s?.disposition;
                  const windowState = s?.windowState;
                  const winValue = s?.pitWindow?.value;
                  const windowText = Array.isArray(winValue) ? `L${winValue[0]}-${winValue[1]}` : "—";
                  
                  let planText = "—";
                  if (lifecycle.label) planText = lifecycle.label;
                  else if (strategyLifecycle === "FINAL" || windowState === "FINAL") planText = "FINAL";
                  else if (disposition === "TO_FINISH") planText = "TO FLAG";
                  else if (windowState === "WINDOW_PASSED_EXTENDING") planText = "EXTENDING STINT";
                  else if (windowText !== "—") planText = windowText;

                  return (
                     <tr key={d.number} onClick={() => onSelectDriver(d.number)} className={"clickable " + lifecycleClassName(d)}>
                        <td>{d.position ?? "-"}</td>
                        <td>{d.code ?? d.number}</td>
                        <td><CompoundBadge compound={d.compound} compact /></td>
                        <td>{d.tyre_age ?? "-"}</td>
                        <td>{d.pit_count ?? 0}</td>
                        <td>{s?.dryTyreRequirement === "SATISFIED" ? "✓ satisfied" : s?.dryTyreRequirement === "UNSATISFIED" ? "! spec needed" : "-"}</td>
                        <td>{s?.degradation?.value != null ? `${s.degradation.value}` : "—"}</td>
                        <td>{planText}</td>
                     </tr>
                  );
               })}
            </tbody>
         </table>
      </Panel>
    </div>
  );
}
