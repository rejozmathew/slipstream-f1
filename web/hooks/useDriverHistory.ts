import { useEffect, useState } from "react";

import { slipstreamApi } from "../api/client";
import type { DriverHistory } from "../domain/protocol";

export function useDriverHistory(sessionKey: string | null, driverNumber: string | null) {
  const requestKey = sessionKey && driverNumber ? `${sessionKey}:${driverNumber}` : null;
  const [result, setResult] = useState<{ key: string; history: DriverHistory | null; error: string | null } | null>(null);

  useEffect(() => {
    if (!sessionKey || !driverNumber || !requestKey) return;
    let active = true;
    void slipstreamApi.driverHistory(sessionKey, driverNumber).then((result) => {
      if (active) setResult({ key: requestKey, history: result, error: null });
    }).catch((reason: unknown) => {
      if (active) setResult({ key: requestKey, history: null, error: reason instanceof Error ? reason.message : "Driver history unavailable" });
    });
    return () => { active = false; };
  }, [driverNumber, requestKey, sessionKey]);

  return result?.key === requestKey ? { history: result.history, error: result.error } : { history: null, error: null };
}
