import { formatSector } from "../../domain/format";
import type { SectorStatus } from "../../domain/protocol";
import "./sectorValue.css";

const labels: Record<SectorStatus, string> = {
  SESSION_BEST: "Fastest observed sector in this segment",
  PERSONAL_BEST: "Driver’s best observed sector in this segment",
  SLOWER: "Slower than the driver’s best observed sector in this segment",
  UNKNOWN: "Sector comparison unavailable",
};

export function SectorValue({ value, status = "UNKNOWN" }: { value: number | null | undefined; status?: SectorStatus }) {
  const grade = value == null ? "UNKNOWN" : status;
  const text = formatSector(value ?? null) ?? "—";
  return <span className={`data-value sector-value sector-${grade.toLowerCase()}`} title={labels[grade]} aria-label={`${text} · ${labels[grade]}`}>{text}</span>;
}
