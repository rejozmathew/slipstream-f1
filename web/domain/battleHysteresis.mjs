/**
 * Keep a recommended pair stable for a minimum source-time interval. A missing
 * held pair can switch immediately; otherwise both hold time and score margin
 * must be satisfied.
 */
export function advanceBattleRecommendation(current, candidate, sourceTime, holdSeconds = 20, switchMargin = 8, currentDriversExist = true) {
  if (!candidate || !Number.isFinite(sourceTime)) return current;
  if (!current || sourceTime < current.since) return { candidate, since: sourceTime };
  const same = current.candidate.aheadDriverNumber === candidate.aheadDriverNumber && current.candidate.behindDriverNumber === candidate.behindDriverNumber;
  if (same) return { ...current, candidate };
  const holdExpired = sourceTime - current.since >= holdSeconds * 1000;
  const marginMet = candidate.score >= current.candidate.score + switchMargin;
  return !currentDriversExist || (holdExpired && marginMet) ? { candidate, since: sourceTime } : current;
}
