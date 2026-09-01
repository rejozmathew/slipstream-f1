export function paceChartAvailability(samples) {
  const representativeCount = samples.filter(
    (sample) => sample.quality === "representative"
      && typeof sample.delta === "number"
      && Number.isFinite(sample.delta),
  ).length;
  return {
    available: representativeCount > 0,
    representativeCount,
    excludedCount: samples.length - representativeCount,
  };
}

export function gapChartModel(samples) {
  if (samples.length < 2) return null;
  const values = samples.map((sample) => sample.gapSeconds).filter(Number.isFinite);
  if (values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(max - min, 0.1);
  const points = samples.map((sample, index) => ({
    x: (index / Math.max(samples.length - 1, 1)) * 100,
    y: 34 - ((sample.gapSeconds - min) / range) * 27,
    value: sample.gapSeconds,
  }));
  return { min, max, points };
}

const TERMINAL_TRACK_STATUSES = new Set([
  "RETIRED", "RETIREMENT", "FINISHED", "DNF", "DNS", "DSQ",
  "DISQUALIFIED", "WITHDRAWN", "EXCLUDED",
]);

export function trackMapLifecycleLabel(driver) {
  const classification = String(driver.classification ?? "").toUpperCase();
  if (classification) return classification === "DISQUALIFIED" ? "DSQ" : classification;
  const condition = String(driver.source_condition ?? "").toUpperCase();
  if (condition === "RETIRED_INDICATED") return "RETIRED";
  if (condition === "STOPPED") return "STOPPED";
  const status = String(driver.status ?? "").toUpperCase();
  if (TERMINAL_TRACK_STATUSES.has(status)) return status;
  if (status === "STOPPED") return "STOPPED";
  return null;
}

export function isTrackMapActive(driver) {
  if (trackMapLifecycleLabel(driver) != null) return false;
  const condition = String(driver.source_condition ?? "").toUpperCase();
  const status = String(driver.status ?? "").toUpperCase();
  return condition === "RUNNING"
    || (condition === "UNKNOWN" && ["RUNNING", "RACING", "LIVE"].includes(status))
    || driver.activity === "ON_TRACK";
}

export function trackCoverage(drivers, positionMode) {
  const eligible = drivers.filter((driver) => isTrackMapActive(driver));
  const hasPosition = (driver) => positionMode !== "unavailable" && (
    (positionMode === "precise_xy" && driver.x != null && driver.y != null)
      || driver.track_position != null
  );
  const positioned = eligible.filter(hasPosition);
  const unpositioned = eligible.filter((driver) => !hasPosition(driver));
  return {
    eligible: eligible.length,
    positioned: positioned.length,
    unpositioned: unpositioned.length,
    unpositionedLabels: unpositioned.map((driver) => driver.code ?? driver.number),
    inactiveLabels: drivers.flatMap((driver) => {
      const label = trackMapLifecycleLabel(driver);
      return label == null ? [] : [`${driver.code ?? driver.number} · ${label}`];
    }),
  };
}

export function lapDeficitGap(driver, leader) {
  if (driver.position === 1) return null;
  const raw = driver.gap_to_leader;
  const available = driver.availability?.gap_to_leader !== "unavailable";
  if (available && raw != null && Number.isFinite(Number(String(raw).replace(/^\+/, "")))) {
    return null;
  }
  if (!Number.isInteger(leader?.lap) || !Number.isInteger(driver.lap)) return null;
  const deficit = leader.lap - driver.lap;
  if (deficit < 1) return null;
  return `+${deficit} ${deficit === 1 ? "LAP" : "LAPS"}`;
}

const FACTOR_UNITS = {
  current_gap: "s",
  relative_degradation: "s/lap",
  representative_pace: "s",
  tyre_age_offset: "laps",
  position_significance: "position",
  pit_window_overlap: "laps",
};

export function battleFactorPresentation(factor) {
  const name = factor.name.replaceAll("_", " ").toUpperCase();
  const unit = FACTOR_UNITS[factor.name] ?? "raw";
  return {
    contributionLabel: `${name} CONTRIBUTION`,
    contribution: `${factor.weight >= 0 ? "+" : ""}${factor.weight.toFixed(1)} PTS`,
    raw: factor.value == null ? "RAW —" : `RAW ${factor.value} ${unit}`,
  };
}

export function battleGapPresentation(candidate) {
  if (candidate?.gapBasis === "interval_to_ahead") {
    return {
      label: "PAIR INTERVAL · SOURCE FEED",
      note: "SEPARATE FROM GAP-TO-LEADER UPDATES · NOT SAME-SNAPSHOT ARITHMETIC",
      sameSnapshotArithmetic: false,
    };
  }
  return {
    label: "PAIR GAP · LATEST SOURCE UPDATES",
    note: "DERIVED FROM SEPARATE GAP-TO-LEADER UPDATES · NOT SAME-SNAPSHOT ARITHMETIC",
    sameSnapshotArithmetic: false,
  };
}
