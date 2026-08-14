import type { ReactNode } from "react";

import { missingLabel } from "../../domain/format";
import type { AvailabilityStatus } from "../../domain/protocol";

type DataValueProps = {
  value: ReactNode | null | undefined;
  availability?: AvailabilityStatus;
  className?: string;
};

export function DataValue({ value, availability, className = "" }: DataValueProps) {
  const missing = value === null || value === undefined || value === "";
  return (
    <span className={`${className} ${missing ? "data-missing" : ""}`.trim()}>
      {missing ? missingLabel(availability) : value}
    </span>
  );
}