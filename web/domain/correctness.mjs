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

export function trackCoverage(drivers, positionMode) {
  const classified = drivers.filter((driver) => driver.position != null);
  const hasPosition = (driver) => positionMode !== "unavailable" && (
    (positionMode === "precise_xy" && driver.x != null && driver.y != null)
      || driver.track_position != null
  );
  const positioned = classified.filter(hasPosition);
  const unpositioned = classified.filter((driver) => !hasPosition(driver));
  return {
    classified: classified.length,
    positioned: positioned.length,
    unpositioned: unpositioned.length,
    unpositionedLabels: unpositioned.map((driver) => driver.code ?? driver.number),
  };
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
