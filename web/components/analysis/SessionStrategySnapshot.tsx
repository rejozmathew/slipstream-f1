import type { AnalyticsSnapshot } from "../../domain/protocol";

type SessionStrategySnapshotProps = {
  analytics: AnalyticsSnapshot | null;
  onOpenStrategy: () => void;
  compact?: boolean;
};

export function SessionStrategySnapshot({ analytics, onOpenStrategy, compact = false }: SessionStrategySnapshotProps) {
  if (!analytics || !analytics.raceRead) {
    return (
      <div className="telemetry-panel">
        <div className="panel-header">
          <span className="panel-title">STRATEGY</span>
          <button type="button" className="panel-action-button" onClick={onOpenStrategy}>VIEW STRATEGY →</button>
        </div>
        <div className="panel-body" style={{ padding: "0.5rem", color: "var(--text-muted)" }}>
          Strategy outlook unavailable.
        </div>
      </div>
    );
  }

  const read = analytics.raceRead;
  
  // Format current tyres
  const currentTyres = Object.entries(read.currentTyreDistribution || {})
    .sort((a, b) => b[1] - a[1])
    .map(([compound, count]) => `○${compound[0]} ${count}`)
    .join("   ");

  // Format stops
  const stopsEntries = Object.entries(read.completedStopDistribution || {})
    .sort((a, b) => b[1] - a[1]);
  const primaryStops = stopsEntries[0] ? `${stopsEntries[0][1]} / ${read.activeRunnerCount} completed ${stopsEntries[0][0]} stops` : "No stops";
  const secondaryStops = stopsEntries[1] ? `${stopsEntries[1][1]} completed ${stopsEntries[1][0]}` : null;

  return (
    <div className="telemetry-panel">
      <div className="panel-header" style={{ display: "flex", justifyContent: "space-between" }}>
        <span className="panel-title">STRATEGY</span>
      </div>
      
      <div className="panel-body" style={{ padding: "0.75rem", fontSize: "0.8rem", lineHeight: "1.4" }}>
        <div style={{ marginBottom: "0.75rem" }}>
          <div style={{ fontSize: "0.65rem", color: "var(--text-muted)", marginBottom: "2px" }}>FIELD</div>
          <div>{primaryStops}</div>
          {secondaryStops && <div>{secondaryStops}</div>}
        </div>
        
        <div style={{ marginBottom: "0.75rem" }}>
          <div style={{ fontSize: "0.65rem", color: "var(--text-muted)", marginBottom: "2px" }}>CURRENT TYRES</div>
          <div>{currentTyres || "None"}</div>
        </div>
        
        <div style={{ marginBottom: "0.75rem" }}>
          <div style={{ fontSize: "0.65rem", color: "var(--text-muted)", marginBottom: "2px" }}>PACE</div>
          <div>Elevated fade · {read.paceTrendDistribution.highFade + read.paceTrendDistribution.moderateFade} / {read.paceTrendDistribution.comparableDrivers} comparable</div>
        </div>
        
        <div style={{ marginBottom: "0.75rem" }}>
          <div style={{ fontSize: "0.65rem", color: "var(--text-muted)", marginBottom: "2px" }}>DRY RULE</div>
          <div>{read.dryRequirementLandscape.unsatisfied} active runner{read.dryRequirementLandscape.unsatisfied !== 1 ? 's' : ''} still owes another spec</div>
        </div>
        
        <div style={{ marginTop: "0.5rem", textAlign: "right" }}>
          <button
            type="button"
            className="panel-action-button"
            onClick={onOpenStrategy}
            style={{
              cursor: "pointer",
              fontSize: "0.72rem",
              fontWeight: 700,
              letterSpacing: "0.06em",
              padding: "3px 8px",
              border: "1px solid var(--line-subtle, #333)",
              background: "var(--bg-surface, #1e1e1e)",
              color: "var(--text-main, #eee)",
              borderRadius: "3px",
            }}
          >
            OPEN STRATEGY →
          </button>
        </div>
      </div>
    </div>
  );
}
