import type { AvailabilityStatus } from "./protocol";

export function formatSessionDate(value: string | null) {
  if (!value) return "?";
  return new Intl.DateTimeFormat("en", {
    day: "2-digit", month: "short", year: "numeric", timeZone: "UTC",
  }).format(new Date(value)).toUpperCase();
}

export function formatDuration(seconds: number) {
  const safe = Math.max(0, Math.round(seconds));
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const remainder = safe % 60;
  return hours > 0
    ? `${hours}:${minutes.toString().padStart(2, "0")}:${remainder.toString().padStart(2, "0")}`
    : `${minutes}:${remainder.toString().padStart(2, "0")}`;
}

export function formatSector(value: number | null) {
  return value == null ? null : value.toFixed(3);
}

export function formatLapTime(value: number | null | undefined) {
  if (value == null) return "—";
  const minutes = Math.floor(value / 60);
  const seconds = value - minutes * 60;
  return minutes > 0 ? `${minutes}:${seconds.toFixed(3).padStart(6, "0")}` : seconds.toFixed(3);
}

export function utcOffsetLabel(offset: string | null) {
  if (!offset) return "";
  const parts = offset.match(/^([+-]?)(\d{2}):(\d{2})/);
  if (!parts) return `UTC${offset}`;
  return `UTC${parts[1] || "+"}${parts[2]}:${parts[3]}`;
}

export function missingLabel(status?: AvailabilityStatus) {
  if (status === "unsupported") return "UNSUPPORTED";
  if (status === "stale") return "STALE";
  return "UNKNOWN";
}
