import type { Driver } from "./protocol";

export type DriverLifecycle = {
  status: string;
  label: string | null;
  terminal: boolean;
  stopped: boolean;
  retiredIndicated: boolean;
  inPit: boolean;
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

const terminalClassificationLabels: Record<string, string> = {
  RETIRED: "RET",
  DNF: "DNF",
  DSQ: "DSQ",
  DNS: "DNS",
  WITHDRAWN: "WD",
  EXCLUDED: "WD",
  FINISHED: "FINISHED",
};

export function canonicalDriverStatus(value: unknown): string {
  const raw = String(value ?? "").trim().toUpperCase();
  return aliases[raw] ?? raw ?? "UNKNOWN";
}

type LifecycleDriver = Pick<Driver, "status" | "position"> & Partial<Pick<Driver, "activity" | "classification" | "source_condition" | "source_retired" | "source_stopped">>;

export function driverClassificationLabel(driver: LifecycleDriver): string | null {
  if (driver.classification) return terminalClassificationLabels[canonicalDriverStatus(driver.classification)] ?? driver.classification;
  if (driver.source_condition && driver.source_condition !== "UNKNOWN") return null;
  return terminalClassificationLabels[canonicalDriverStatus(driver.status)] ?? null;
}

export function driverLifecycle(driver: LifecycleDriver): DriverLifecycle {
  const classification = driverClassificationLabel(driver);
  const condition = driver.source_condition && driver.source_condition !== "UNKNOWN"
    ? driver.source_condition
    : canonicalDriverStatus(driver.status) === "RETIRED" ? "RETIRED_INDICATED"
      : canonicalDriverStatus(driver.status);
  const status = driver.classification ?? condition;
  const terminal = classification != null;
  const stopped = !terminal && condition === "STOPPED";
  const retiredIndicated = !terminal && condition === "RETIRED_INDICATED";
  const inPit = !terminal && (condition === "IN_PIT" || (condition === "RUNNING" && driver.activity === "IN_PIT"));
  const circulating = !terminal && condition === "RUNNING" && !inPit;
  return {
    status,
    label: classification ?? (retiredIndicated ? "RETIRED" : stopped ? "STOPPED" : inPit ? "IN PIT" : null),
    terminal,
    stopped,
    retiredIndicated,
    inPit,
    circulating,
    battleEligible: circulating && driver.position != null,
  };
}

export function lifecycleClassName(driver: LifecycleDriver): string {
  const lifecycle = driverLifecycle(driver);
  if (lifecycle.terminal) return "driver-terminal";
  if (lifecycle.stopped) return "driver-stopped";
  if (lifecycle.retiredIndicated) return "driver-retired-indicated";
  if (!lifecycle.circulating) return "driver-lifecycle-unknown";
  return "driver-running";
}
