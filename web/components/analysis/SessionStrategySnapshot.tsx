import type { AnalyticsSnapshot } from "../../domain/protocol";
import { StrategyOutlook } from "./StrategyOutlook";

type SessionStrategySnapshotProps = {
  analytics: AnalyticsSnapshot | null;
  onOpenStrategy: () => void;
  compact?: boolean;
};

export function SessionStrategySnapshot({ analytics, onOpenStrategy, compact = false }: SessionStrategySnapshotProps) {
  return (
    <StrategyOutlook
      analytics={analytics}
      compact={compact}
      action={
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
          VIEW STRATEGY →
        </button>
      }
    />
  );
}
