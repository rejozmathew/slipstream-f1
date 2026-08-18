import { useMemo } from "react";

import type { AnalyticsSnapshot, BattleCandidate, RaceState } from "../domain/protocol";

/**
 * v2.1 §20 / invariant 6: the Battle recommendation is SERVER-stabilized
 * (session-scoped, cursor-keyed hysteresis owned by `AnalyticsService`).
 * The client renders the published `stabilizedRecommended` verbatim and must
 * NOT recompute hysteresis locally (the prior `battleHysteresis.mjs` advance
 * loop is retired).
 */
export function useBattleRecommendation(analytics: AnalyticsSnapshot | null, state: RaceState) {
  void state;
  return useMemo(() => {
    const stabilized = analytics?.battle.stabilizedRecommended as BattleCandidate | null | undefined;
    if (!stabilized || stabilized.aheadDriverNumber == null || stabilized.behindDriverNumber == null) return null;
    return [stabilized.aheadDriverNumber, stabilized.behindDriverNumber] as [string, string];
  }, [analytics?.battle.stabilizedRecommended]);
}
