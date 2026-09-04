export const NO_SPECIFIC_PIRELLI_STRATEGY = "No specific Pirelli tyre strategy published.";

const contextPriority = ["COMPOUND_OUTLOOK", "STRATEGY_OUTLOOK", "DEGRADATION", "TYRE_STRESS", "WEATHER", "TRACK_EVOLUTION", "GRIP"];

const compoundCodes = {
  HARD: "H",
  MEDIUM: "M",
  SOFT: "S",
  INTERMEDIATE: "I",
  WET: "W",
};

export function compoundCode(compound) {
  if (!compound) return "—";
  return compoundCodes[compound.toUpperCase()] ?? compound;
}

export function nominationSummary(selection) {
  if (!selection) return null;
  return `${selection.hard} HARD · ${selection.medium} MEDIUM · ${selection.soft} SOFT`;
}

export function prioritizedPirelliContextFacts(facts = [], limit = 5) {
  const priority = new Map(contextPriority.map((category, index) => [category, index]));
  const seenCategories = new Set();
  const seenStatements = new Set();
  const ranked = facts
    .map((fact, index) => ({ fact, index }))
    .sort((left, right) => (priority.get(left.fact.category) ?? contextPriority.length) - (priority.get(right.fact.category) ?? contextPriority.length) || left.index - right.index);
  const selected = [];
  for (const item of ranked) {
    const statement = item.fact.statement.trim().toLowerCase();
    if (seenCategories.has(item.fact.category) || seenStatements.has(statement)) continue;
    selected.push(item.fact);
    seenCategories.add(item.fact.category);
    seenStatements.add(statement);
    if (selected.length === limit) return selected;
  }
  for (const item of ranked) {
    const statement = item.fact.statement.trim().toLowerCase();
    if (seenStatements.has(statement)) continue;
    selected.push(item.fact);
    seenStatements.add(statement);
    if (selected.length === limit) break;
  }
  return selected;
}

export function optionPathText(option) {
  if (!option?.compounds?.length) return "—";
  const separator = option.order === "ORDERED" ? " → " : " + ";
  return option.compounds.map(compoundCode).join(separator);
}

export function optionOrderNote(option) {
  if (option.order === "ANY_ORDER") return "Compounds may be used in either order.";
  if (option.order === "PARTIALLY_ORDERED") return "Only part of the compound order was specified.";
  if (option.order === "UNKNOWN") return "Compound order was not specified.";
  return null;
}

export function optionWindowText(option) {
  if (!option?.pitWindows?.length) return "No stop lap was published.";
  return option.pitWindows
    .map((window, index) => window ? `Stop ${index + 1}: L${window.startLap}–${window.endLap}` : `Stop ${index + 1}: no lap published`)
    .join(" · ");
}

export function optionDeltaText(option) {
  if (option?.publishedDeltaSeconds != null) return `Published delta · +${option.publishedDeltaSeconds.toFixed(1)}s`;
  if (option?.publishedDeltaSecondsRange) return `Published delta · +${option.publishedDeltaSecondsRange[0].toFixed(1)}–${option.publishedDeltaSecondsRange[1].toFixed(1)}s`;
  return null;
}

export function relevantPublishedOptions(baseline, driver) {
  if (baseline?.status !== "PRESENT" || !baseline.options?.length) return [];
  const references = new Map((driver?.pirelliReferences ?? []).map((reference) => [reference.optionId, reference]));
  const meaningful = baseline.options.filter((option) => {
    const status = references.get(option.id)?.status;
    return status && !["NO_MATCH", "NOT_COMPARABLE", "UNKNOWN"].includes(status);
  });
  if (meaningful.length > 0) return meaningful;
  const compatibleIds = new Set(driver?.compatibleOptionIds ?? []);
  if (compatibleIds.size > 0) {
    const resolved = baseline.options.filter((option) => compatibleIds.has(option.id));
    if (resolved.length > 0) return resolved;
  }
  return baseline.options;
}

export function driverStrategyRelationship(baseline, driver) {
  if (baseline?.status !== "PRESENT") return null;
  if (!baseline.options?.length) return NO_SPECIFIC_PIRELLI_STRATEGY;
  if (driver?.pirelliSummary) return driver.pirelliSummary;
  switch (driver?.relation) {
    case "MATCHING_ONE":
      return "A published Pirelli tyre strategy is still applicable.";
    case "MATCHING_MULTIPLE":
      return "More than one published Pirelli tyre strategy is still applicable.";
    case "DIVERGED":
      return "No published Pirelli tyre strategy matches the actual tyre strategy.";
    case "TERMINAL":
      return "Published Pirelli tyre strategies are shown for retrospective comparison.";
    case "NOT_COMPARABLE":
    case "UNKNOWN":
    default:
      return "Published Pirelli tyre strategies are shown as pre-race reference.";
  }
}

export function actualStrategyCompounds(driver) {
  return driver?.actualStrategy?.compounds ?? driver?.observedCompounds ?? [];
}

export function actualStrategyText(driver) {
  const compounds = actualStrategyCompounds(driver);
  return compounds.length ? compounds.map(compoundCode).join(" → ") : "—";
}

export function dryTyreRequirementText(driver) {
  if (driver?.dryTyreRequirement === "UNSATISFIED") return "Another dry compound required";
  if (driver?.dryTyreRequirement === "SATISFIED") return "Dry tyre requirement satisfied";
  return null;
}

function stopComparisonText(comparison) {
  const published = comparison.publishedStartLap == null || comparison.publishedEndLap == null
    ? "No stop lap published"
    : `Pirelli L${comparison.publishedStartLap}–${comparison.publishedEndLap}`;
  if (comparison.actualLap == null) return published;
  return `Actual L${comparison.actualLap} · ${published}`;
}

function assessmentText(status) {
  return {
    STILL_APPLICABLE: "Still applicable",
    ALIGNED: "Strategy and timing aligned",
    SAME_COMPOUNDS_DIFFERENT_TIMING: "Same compounds · different timing",
    SAME_COMPOUNDS_TIMING_UNKNOWN: "Same compounds · timing unavailable",
    EXTRA_SAME_COMPOUND_STOP: "Additional same-compound stop",
    NO_MATCH: "No match",
    NOT_COMPARABLE: "Pre-race reference",
    REFERENCE_ONLY: "Pre-race reference",
    UNKNOWN: "Comparison unavailable",
  }[status] ?? null;
}

export function driverPirelliReferenceRows(baseline, driver) {
  const references = new Map((driver?.pirelliReferences ?? []).map((reference) => [reference.optionId, reference]));
  return relevantPublishedOptions(baseline, driver).map((option) => {
    const reference = references.get(option.id);
    const windows = option.pitWindows.map((publishedWindow, stopIndex) => {
      const comparison = reference?.stopComparisons?.find((item) => item.stopIndex === stopIndex);
      if (comparison) {
        const comparisonWithheld = ["REFERENCE_ONLY", "NOT_COMPARABLE", "UNKNOWN"].includes(reference?.status);
        return {
          stopIndex,
          range: stopComparisonText(comparison),
          state: comparisonWithheld ? null : comparison.status === "INSIDE" ? "ALIGNED" : comparison.status === "OUTSIDE" ? "DIFFERENT TIMING" : comparison.status === "NOT_OCCURRED" ? "NOT STOPPED" : null,
        };
      }
      if (!publishedWindow) return { stopIndex, range: "No stop lap published", state: null };
      return {
        stopIndex,
        range: `Pirelli L${publishedWindow.startLap}–${publishedWindow.endLap}`,
        state: null,
      };
    });
    return {
      id: option.id,
      rank: option.rank,
      compounds: option.compounds,
      sequence: optionPathText(option),
      ordered: option.order === "ORDERED",
      orderNote: optionOrderNote(option),
      assessment: reference?.status ?? driver?.pirelliAssessment ?? "UNKNOWN",
      assessmentText: assessmentText(reference?.status ?? driver?.pirelliAssessment ?? "UNKNOWN"),
      windows,
    };
  });
}

export function driverPirelliStrategiesText(baseline, driver) {
  if (baseline?.status !== "PRESENT") return "—";
  if (!baseline.options?.length) return NO_SPECIFIC_PIRELLI_STRATEGY;
  return relevantPublishedOptions(baseline, driver).map(optionPathText).join(" / ") || "Pirelli tyre strategy available";
}

export function driverPirelliStopWindowsText(baseline, driver, final = false) {
  if (final) return "Final · retrospective";
  if (baseline?.status !== "PRESENT" || !baseline.options?.length) return "—";
  const rows = driverPirelliReferenceRows(baseline, driver);
  const multiple = rows.length > 1;
  return rows.map((row) => {
    const windows = row.windows.map((window) => window.range).join(", ") || "No stop lap published";
    return multiple ? `${row.sequence}: ${windows}` : windows;
  }).join(" · ") || "No stop lap published";
}

// Compatibility aliases for downstream integrations; current product surfaces use
// the tyre-strategy names above.
export const driverPublishedRouteRows = driverPirelliReferenceRows;
export const driverPublishedRoutesText = driverPirelliStrategiesText;
export const driverPublishedWindowsText = driverPirelliStopWindowsText;
