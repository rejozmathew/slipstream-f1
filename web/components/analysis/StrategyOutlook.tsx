import { Panel } from "../shared/Panel";

type StrategyOutlookProps = {
  compact?: boolean;
};

export function StrategyOutlook({ compact = false }: StrategyOutlookProps) {
  return (
    <Panel
      eyebrow="STRATEGY"
      title="Strategy Outlook"
      className={`strategy-panel${compact ? " strategy-panel-compact" : ""}`}
      action={<span className="panel-badge">ANALYTICS NOT ENABLED</span>}
    >
      <div className="strategy-unavailable" role="status">
        <strong>NOT AVAILABLE YET</strong>
        <p>Strategy will appear here when the production analytics model has sufficient evidence.</p>
      </div>
    </Panel>
  );
}
