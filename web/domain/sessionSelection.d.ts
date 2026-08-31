import type { CatalogSession } from "./protocol";

export function preferredWeekendSession(
  sessions: CatalogSession[],
  currentSessionKey?: string | null,
): CatalogSession | null;
