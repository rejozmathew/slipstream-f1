import type { Driver } from "./protocol";

// v2.1 §8.3 / §17: a single terminal-status vocabulary shared with the
// backend `lifecycle` module (src/slipstream/lifecycle.py). A driver in any
// of these states is never a Battle candidate; STOPPED is active for the
// field but not circulating, so it is also excluded from Battle.
const BATTLE_INELIGIBLE_STATUSES = new Set([
  "RETIRED",
  "WITHDRAWN",
  "DNS",
  "DNF",
  "DSQ",
  "DISQUALIFIED",
  "RETIREMENT",
  "NOT_STARTING",
  "SCRATCHED",
  "STOPPED",
]);

export function isBattleEligible(driver: Driver): boolean {
  const status = (driver.status ?? "").toUpperCase();
  return !BATTLE_INELIGIBLE_STATUSES.has(status);
}

export function numericGap(value: string | null): number | null {
  if (!value) return null;
  const match = value.replace(",", ".").match(/-?\d+(?:\.\d+)?/);
  if (!match || /lap/i.test(value)) return null;
  const parsed = Number(match[0]);
  return Number.isFinite(parsed) ? parsed : null;
}

export function gapFromLeader(driver: Driver): number | null {
  return driver.position === 1 ? 0 : numericGap(driver.gap_to_leader);
}

export function gapBetween(left: Driver | null, right: Driver | null): number | null {
  if (!left || !right) return null;
  const leftGap = gapFromLeader(left);
  const rightGap = gapFromLeader(right);
  return leftGap == null || rightGap == null ? null : Math.abs(rightGap - leftGap);
}

/**
 * v2.1 §15.2: ONE server-provided gap truth. When the pair is a server
 * candidate, the visible "current gap" is the server's published `gapSeconds`
 * (scored on interval-to-ahead) — NOT a client recompute from gap-to-leader,
 * which yields the "RECOMMENDED BATTLE / OBSERVED GAP —" defect for a live
 * battle whose gap-to-leader is missing. Falls back to the derived
 * gap-to-leader value only for non-candidate (pinned) pairs.
 */
export function currentPairGap(
  analytics: import("./protocol").AnalyticsSnapshot | null,
  left: Driver | null,
  right: Driver | null,
): number | null {
  if (!left || !right) return null;
  const candidates = analytics?.battle.candidates ?? [];
  const match =
    candidates.find(
      (item) =>
        item.aheadDriverNumber === left.number &&
        item.behindDriverNumber === right.number,
    ) ??
    candidates.find(
      (item) =>
        item.aheadDriverNumber === right.number &&
        item.behindDriverNumber === left.number,
    );
  if (match && typeof match.gapSeconds === "number") return match.gapSeconds;
  return gapBetween(left, right);
}

export function recommendedBattle(drivers: Driver[]): [Driver, Driver] | null {
  const ordered = [...drivers]
    .filter((driver) => driver.position != null && isBattleEligible(driver))
    .sort((a, b) => (a.position ?? 999) - (b.position ?? 999));
  let best: [Driver, Driver] | null = null;
  let bestGap = Number.POSITIVE_INFINITY;
  for (let index = 1; index < ordered.length; index += 1) {
    const gap = numericGap(ordered[index].interval_to_ahead);
    if (gap != null && gap < bestGap) {
      best = [ordered[index - 1], ordered[index]];
      bestGap = gap;
    }
  }
  return best ?? (ordered.length >= 2 ? [ordered[0], ordered[1]] : null);
}

