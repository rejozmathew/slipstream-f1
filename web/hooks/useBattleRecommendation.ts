import { useEffect, useMemo, useState } from "react";

import type { AnalyticsSnapshot, BattleCandidate, RaceState } from "../domain/protocol";
import { advanceBattleRecommendation } from "../domain/battleHysteresis.mjs";

type HeldRecommendation = { candidate: BattleCandidate; since: number };

export function useBattleRecommendation(analytics: AnalyticsSnapshot | null, state: RaceState) {
  const candidate = analytics?.battle.recommended ?? null;
  const holdSeconds = analytics?.battle.hysteresis.minimumHoldSeconds ?? 20;
  const switchMargin = analytics?.battle.hysteresis.switchMargin ?? 8;
  const sourceTime = Date.parse(analytics?.asOf ?? state.updated_at ?? "");
  const [held, setHeld] = useState<HeldRecommendation | null>(null);

  useEffect(() => {
    if (!candidate || !Number.isFinite(sourceTime)) return;
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      setHeld((current) => {
        const ahead = current ? state.drivers[current.candidate.aheadDriverNumber] : null;
        const behind = current ? state.drivers[current.candidate.behindDriverNumber] : null;
        const currentPairValid = !current || Boolean(
          ahead?.position != null
          && behind?.position != null
          && behind.position === ahead.position + 1
        );
        return advanceBattleRecommendation(current, candidate, sourceTime, holdSeconds, switchMargin, currentPairValid);
      });
    });
    return () => { active = false; };
  }, [candidate, holdSeconds, sourceTime, state.drivers, switchMargin]);

  return useMemo(() => held ? [held.candidate.aheadDriverNumber, held.candidate.behindDriverNumber] as [string, string] : null, [held]);
}
