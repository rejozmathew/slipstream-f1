import type { Driver } from "./protocol";

export type DriverLifecycle = {
  status: string;
  label: string | null;
  terminal: boolean;
  stopped: boolean;
  noRecentProgress: boolean;
  circulating: boolean;
  battleEligible: boolean;
};

const aliases: Record<string, string> = {
  "": "UNKNOWN",
  RACING: "RUNNING",
  LIVE: "RUNNING",
  STARTED: "RUNNING",
  RETIREMENT: "RETIRED",
  DISQUALIFIED: "DSQ",
  DID_NOT_START: "DNS",
  NOT_STARTING: "DNS",
  SCRATCHED: "DNS",
};

const terminalLabels: Record<string, string> = {
  RETIRED: "RETIRED",
  FINISHED: "FINISHED",
  DNF: "DNF",
  DSQ: "DSQ",
  DNS: "DNS",
  WITHDRAWN: "WITHDRAWN",
  EXCLUDED: "WITHDRAWN",
};

export function canonicalDriverStatus(value: unknown): string {
  const raw = String(value ?? "").trim().toUpperCase();
  return aliases[raw] ?? raw ?? "UNKNOWN";
}

export function driverLifecycle(driver: Pick<Driver, "status" | "position"> & Partial<Pick<Driver, "activity">>): DriverLifecycle {
  const status = canonicalDriverStatus(driver.status);
  const terminal = status in terminalLabels;
  const stopped = status === "STOPPED";
  const noRecentProgress = driver.activity === "NO_RECENT_PROGRESS" && !terminal && !stopped;
  const circulating = status === "RUNNING";
  return {
    status,
    label: stopped ? "STOPPED" : terminalLabels[status] ?? (noRecentProgress ? "NO RECENT PROGRESS" : null),
    terminal,
    stopped,
    noRecentProgress,
    circulating,
    battleEligible: circulating && !noRecentProgress && driver.position != null,
  };
}

export function lifecycleClassName(driver: Pick<Driver, "status" | "position"> & Partial<Pick<Driver, "activity">>): string {
  const lifecycle = driverLifecycle(driver);
  if (lifecycle.terminal) return "driver-terminal";
  if (lifecycle.stopped) return "driver-stopped";
  if (lifecycle.noRecentProgress) return "driver-no-recent-progress";
  if (!lifecycle.circulating) return "driver-lifecycle-unknown";
  return "driver-running";
}
