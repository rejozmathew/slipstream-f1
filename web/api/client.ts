import type { AnalyticsSnapshot, DriverHistory, ReplayCatalog, ReplayMetadata, SourceCapabilities, StateEnvelope, ViewingMode } from "../domain/protocol";

const configuredBase = (import.meta.env.VITE_SLIPSTREAM_API ?? "").replace(/\/$/, "");
export type DownloadJob = { sessionKey: string; status: "QUEUED" | "DOWNLOADING" | "FINALIZING" | "AVAILABLE" | "FAILED"; error: string | null };

function url(path: string, sessionKey?: string | null) {
  const query = sessionKey ? `?session_key=${encodeURIComponent(sessionKey)}` : "";
  return `${configuredBase}${path}${query}`;
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = `Request failed with HTTP ${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: string };
      detail = payload.detail ?? detail;
    } catch {
      // The status remains actionable when the response has no JSON body.
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export const slipstreamApi = {
  catalog: () => fetch(url("/api/v1/catalog"), { cache: "no-store", signal: AbortSignal.timeout(8000) }).then(readJson<ReplayCatalog>),
  state: (sessionKey: string, mode: ViewingMode, sequence?: number, delaySeconds = 0) => fetch(`${url("/api/v1/state", sessionKey)}&mode=${mode}&delay_seconds=${delaySeconds}${sequence == null ? "&at=start" : `&seq=${sequence}`}`, { cache: "no-store", signal: AbortSignal.timeout(8000) }).then(readJson<StateEnvelope>),
  replay: (sessionKey?: string | null) => fetch(url("/api/v1/replay", sessionKey), { cache: "no-store" }).then(readJson<ReplayMetadata>),
  capabilities: (sessionKey?: string | null) => fetch(url("/api/v1/capabilities", sessionKey), { cache: "no-store" }).then(readJson<SourceCapabilities>),
  driverHistory: (sessionKey: string, driverNumber: string) => fetch(`${configuredBase}/api/v1/driver-history?session_key=${encodeURIComponent(sessionKey)}&driver_number=${encodeURIComponent(driverNumber)}`, { cache: "no-store" }).then(readJson<DriverHistory>),
  analytics: (sessionKey: string, sequence?: number) => fetch(`${configuredBase}/api/v1/analytics?session_key=${encodeURIComponent(sessionKey)}${sequence == null ? "" : `&seq=${sequence}`}`, { cache: "no-store", signal: AbortSignal.timeout(15000) }).then(readJson<AnalyticsSnapshot>),
  download: (sessionKey: string) => fetch(url("/api/v1/download", sessionKey), { method: "POST" }).then(readJson<DownloadJob>),
  jobs: () => fetch(url("/api/v1/jobs"), { cache: "no-store", signal: AbortSignal.timeout(8000) }).then(readJson<{ jobs: DownloadJob[] }>),
  streamUrl(sessionKey?: string | null, mode?: ViewingMode, sequence?: number, delaySeconds = 0) {
    const base = configuredBase
      ? configuredBase.replace(/^http/, "ws")
      : `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}`;
    const params = new URLSearchParams();
    if (sessionKey) params.set("session_key", sessionKey);
    if (mode) params.set("mode", mode);
    if (sequence != null && mode !== "live") params.set("seq", String(sequence));
    if (mode === "live") params.set("delay_seconds", String(delaySeconds));
    const query = params.size ? `?${params.toString()}` : "";
    return `${base}/api/v1/stream${query}`;
  },
};
