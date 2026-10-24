import type { CatalogSession } from "./protocol";

export function preferredWeekendSession(
  sessions: CatalogSession[],
  currentSessionKey?: string | null,
): CatalogSession | null;


export type CatalogWeekend = CatalogSession & {
  sessions: CatalogSession[];
  group: "races" | "cancelled" | "testing";
  label: string;
};
export function orderedSeasonWeekends(sessions: CatalogSession[], year: number | null): CatalogWeekend[];
export function catalogMeetingLabel(session: CatalogSession): string;
