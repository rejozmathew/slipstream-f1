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

export function utcOffsetLabel(offset: string | null) {
  if (!offset) return "";
  const sign = offset.startsWith("-") || offset.startsWith("+") ? "" : "+";
  return `UTC${sign}${offset.slice(0, 6)}`;
}

export function missingLabel(status?: AvailabilityStatus) {
  if (status === "unsupported") return "UNSUPPORTED";
  if (status === "stale") return "STALE";
  return "UNKNOWN";
}