import type { Driver } from "./protocol";

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

export function recommendedBattle(drivers: Driver[]): [Driver, Driver] | null {
  const ordered = [...drivers].filter((driver) => driver.position != null).sort((a, b) => (a.position ?? 999) - (b.position ?? 999));
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

