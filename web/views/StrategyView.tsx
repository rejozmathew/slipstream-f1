import { useMemo } from "react";
import { Panel } from "../components/shared/Panel";
import { CompoundBadge } from "../components/shared/CompoundBadge";
import type { AnalyticsSnapshot, RaceState } from "../domain/protocol";

type StrategyViewProps = {
  state: RaceState;
  analytics: AnalyticsSnapshot | null;
  onSelectDriver: (driverNumber: string) => void;
};

export function StrategyView({ state, analytics, onSelectDriver }: StrategyViewProps) {
  const drivers = useMemo(() => Object.values(state.drivers).sort((a, b) => (a.position ?? 999) - (b.position ?? 999)), [state.drivers]);
  const read = analytics?.raceRead;
  const validity = analytics?.strategyValidity ?? "UNAVAILABLE";

  const sessionName = state.session.meeting_name ? `${state.session.meeting_name.toUpperCase()} GRAND PRIX` : "GRAND PRIX";
  const lapText = state.session.total_laps ? `LAP ${state.session.lap || 0} / ${state.session.total_laps}` : `LAP ${state.session.lap || 0}`;
  const trackStatus = state.session.track_status || "GREEN";

  return (
    <div className="strategy-view">
      <header className="experience-heading" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h1 style={{ fontSize: "1.2rem", margin: 0 }}>STRATEGY &middot; {sessionName}</h1>
        </div>
        <div style={{ textAlign: "right" }}>
          <span style={{ fontWeight: "bold", marginRight: "1rem" }}>{lapText} &middot; {trackStatus.toUpperCase()}</span>
          <span className="strategy-validity-state">OUTLOOK: {validity}</span>
        </div>
      </header>
      
      {read && (
        <div className="strategy-grid" style={{ marginBottom: "1rem", display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "1rem" }}>
          <Panel title="Field">
            <div className="panel-body">
              {Object.entries(read.completedStopDistribution || {}).sort((a, b) => b[1] - a[1]).map(([c, n]) => (
                <div key={c}>{n} / {read.activeRunnerCount} completed {c} stops</div>
              ))}
            </div>
          </Panel>
          <Panel title="Current Tyres">
            <div className="panel-body">
              {Object.entries(read.currentTyreDistribution || {}).sort((a, b) => b[1] - a[1]).map(([c, n]) => (
                <span key={c} style={{ marginRight: "1rem" }}>○{c[0]} {n}</span>
              ))}
            </div>
          </Panel>
          <Panel title="Pace">
            <div className="panel-body">
              <div>Elevated fade &middot; {read.paceTrendDistribution.highFade + read.paceTrendDistribution.moderateFade} / {read.paceTrendDistribution.comparableDrivers} comparable</div>
            </div>
          </Panel>
          <Panel title="Dry Rule">
            <div className="panel-body">
              <div>{read.dryRequirementLandscape.unsatisfied} active runner{read.dryRequirementLandscape.unsatisfied !== 1 ? 's' : ''} still owes another spec</div>
            </div>
          </Panel>
        </div>
      )}
      
      <div style={{ display: "grid", gridTemplateColumns: "3fr 1fr", gap: "1rem" }}>
        <Panel title="Driver Strategies" className="driver-strategy-panel">
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
                    const s = analytics?.drivers[d.number]?.strategy;
                    const disposition = s?.disposition;
                    const windowState = s?.windowState;
                    const winValue = s?.pitWindow?.value;
                    const windowText = Array.isArray(winValue) ? `L${winValue[0]}-${winValue[1]}` : "—";
                    
                    let planText = "—";
                    if (s?.terminalState) planText = s.terminalState;
                    else if (disposition === "TO_FINISH") planText = "TO FLAG";
                    else if (windowState === "WINDOW_PASSED_EXTENDING") planText = "EXTENDING STINT";
                    else if (windowText !== "—") planText = windowText;

                    return (
                       <tr key={d.number} onClick={() => onSelectDriver(d.number)} className="clickable">
                          <td className={s?.terminalState ? "terminal" : ""}>{d.position ?? "-"}</td>
                          <td>{d.code ?? d.number}</td>
                          <td><CompoundBadge compound={d.compound} compact /></td>
                          <td>{d.tyre_age ?? "-"}</td>
                          <td>{d.pit_count ?? 0}</td>
                          <td>{s?.dryTyreRequirement === "SATISFIED" ? "✓ satisfied" : s?.dryTyreRequirement === "UNSATISFIED" ? "! spec needed" : "-"}</td>
                          <td>{s?.degradation?.value ? `${s.degradation.value}` : "stable"}</td>
                          <td>{planText}</td>
                       </tr>
                    );
                 })}
              </tbody>
           </table>
        </Panel>
        
        <Panel title="Pace & Stints">
           <div className="panel-body" style={{ padding: "1rem", color: "var(--text-muted)", fontSize: "0.85rem", fontStyle: "italic" }}>
             Pace analysis not yet implemented.
           </div>
        </Panel>
      </div>
    </div>
  );
}
