import type { Driver } from "./protocol";

export type DriverLifecycle = {
  status: string;
  label: string | null;
  terminal: boolean;
  stopped: boolean;
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

export function driverLifecycle(driver: Pick<Driver, "status" | "position">): DriverLifecycle {
  const status = canonicalDriverStatus(driver.status);
  const terminal = status in terminalLabels;
  const stopped = status === "STOPPED";
  const circulating = status === "RUNNING";
  return {
    status,
    label: stopped ? "STOPPED" : terminalLabels[status] ?? null,
    terminal,
    stopped,
    circulating,
    battleEligible: circulating && driver.position != null,
  };
}

export function lifecycleClassName(driver: Pick<Driver, "status" | "position">): string {
  const lifecycle = driverLifecycle(driver);
  if (lifecycle.terminal) return "driver-terminal";
  if (lifecycle.stopped) return "driver-stopped";
  if (!lifecycle.circulating) return "driver-lifecycle-unknown";
  return "driver-running";
}
