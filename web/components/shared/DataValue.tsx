import type { ReactNode } from "react";

import { missingLabel } from "../../domain/format";
import type { AvailabilityStatus } from "../../domain/protocol";

type DataValueProps = {
  value: ReactNode | null | undefined;
  availability?: AvailabilityStatus;
  className?: string;
  compact?: boolean;
};

export function DataValue({ value, availability, className = "", compact = false }: DataValueProps) {
  const missing = value === null || value === undefined || value === "";
  const label = missingLabel(availability);
  return (
    <span
      className={`data-value ${className} ${missing ? "data-missing" : ""} ${availability === "stale" ? "data-stale" : ""}`.trim()}
      title={missing && compact ? label : undefined}
      aria-label={missing && compact ? label : undefined}
    >
      {missing ? compact ? "\u2014" : label : value}
    </span>
  );
}
