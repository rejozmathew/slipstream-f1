type CompoundBadgeProps = {
  compound?: string | null;
  compact?: boolean;
  showLabel?: boolean;
};

const labels: Record<string, string> = {
  SOFT: "S",
  MEDIUM: "M",
  HARD: "H",
  INTERMEDIATE: "I",
  WET: "W",
};

export function normalizeCompound(compound?: string | null) {
  const value = compound?.trim().toUpperCase();
  if (value === "INTER" || value === "INT") return "INTERMEDIATE";
  return value && labels[value] ? value : null;
}

export function CompoundBadge({ compound, compact = false, showLabel = false }: CompoundBadgeProps) {
  const normalized = normalizeCompound(compound);
  if (!normalized) return <span className="compound-badge compound-unknown" aria-label="Compound unavailable">—</span>;
  return <span className={`compound-badge compound-${normalized.toLowerCase()}${compact ? " compound-badge-compact" : ""}`} aria-label={normalized}>
    <i>{labels[normalized]}</i>{showLabel && <em>{normalized}</em>}
  </span>;
}

export function CompoundTransition({ from, to, compact = false }: { from?: string | null; to?: string | null; compact?: boolean }) {
  return <span className="compound-transition">
    <CompoundBadge compound={from} compact={compact} />
    <b aria-hidden="true">→</b>
    <CompoundBadge compound={to} compact={compact} />
  </span>;
}

export function CompoundSequence({ compounds, compact = true, empty = "—", ordered = true }: { compounds?: Array<string | null>; compact?: boolean; empty?: string; ordered?: boolean }) {
  if (!compounds?.length) return <span className="published-path-empty">{empty}</span>;
  return <span className="published-path">{compounds.map((compound, index) => <span key={`${compound ?? "unknown"}-${index}`}>{index > 0 && <i aria-hidden="true">{ordered ? "→" : "+"}</i>}<CompoundBadge compound={compound} compact={compact} /></span>)}</span>;
}

export function StrategyCompoundTransition({ value, compact = false }: { value?: string | null; compact?: boolean }) {
  const parts = value?.split(/\s*(?:→|->)\s*/);
  if (!parts || parts.length !== 2) return <span className="compound-transition">—</span>;
  return <CompoundTransition from={parts[0]} to={parts[1]} compact={compact} />;
}
