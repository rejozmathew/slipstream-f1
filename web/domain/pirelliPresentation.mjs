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
  const relevant = relevantPublishedOptions(baseline, driver);
  switch (driver?.relation) {
    case "MATCHING_ONE":
      return relevant[0] ? `Current path matches the published ${optionPathText(relevant[0])} tyre strategy.` : "Current path matches a published Pirelli tyre strategy.";
    case "MATCHING_MULTIPLE":
      return `Current path remains compatible with ${relevant.length} published tyre strategies.`;
    case "DIVERGED":
      return "No published Pirelli tyre strategy matches the current path.";
    case "TERMINAL":
      return "Published Pirelli tyre strategies are shown for retrospective comparison.";
    case "NOT_COMPARABLE":
    case "UNKNOWN":
    default:
      return "Published Pirelli tyre strategies are shown as pre-race reference.";
  }
}

function windowStateText(state, window, observedLap) {
  if (state === "COMPLETED") return observedLap == null ? "Observed stop completed" : `Observed stop L${observedLap}`;
  if (state === "ACTIVE") return "Published window open now";
  if (state === "PASSED") return "Published window passed";
  if (state === "BEFORE") return `Published window opens L${window.startLap}`;
  return `Published window L${window.startLap}–${window.endLap}`;
}

export function driverPublishedRouteRows(baseline, driver, pitEvents = []) {
  return relevantPublishedOptions(baseline, driver).map((option) => {
    const windows = option.pitWindows.map((publishedWindow, stopIndex) => {
      const driverWindow = driver?.windows?.find((item) => item.optionId === option.id && item.stopIndex === stopIndex);
      const window = driverWindow ?? publishedWindow;
      if (!window) return { stopIndex, range: "No stop lap published", state: null };
      const observed = pitEvents.find((event, index) => (event.ordinal ?? index + 1) === stopIndex + 1);
      return {
        stopIndex,
        range: `L${window.startLap}–${window.endLap}`,
        state: driverWindow ? windowStateText(driverWindow.state, window, observed?.lap) : null,
      };
    });
    return {
      id: option.id,
      rank: option.rank,
      route: optionPathText(option),
      orderNote: optionOrderNote(option),
      windows,
    };
  });
}

export function driverPublishedRoutesText(baseline, driver) {
  if (baseline?.status !== "PRESENT") return "—";
  if (!baseline.options?.length) return "No specific route published";
  return relevantPublishedOptions(baseline, driver).map(optionPathText).join(" / ") || "Published routes available";
}

export function driverPublishedWindowsText(baseline, driver, final = false, pitEvents = []) {
  if (final) return "Final · retrospective";
  if (baseline?.status !== "PRESENT" || !baseline.options?.length) return "—";
  if (pitEvents.length > 0) {
    const rows = driverPublishedRouteRows(baseline, driver, pitEvents);
    const multiple = rows.length > 1;
    return rows.map((row) => {
      const windows = row.windows.map((window) => `${window.range}${window.state ? ` · ${window.state}` : ""}`).join(", ") || "no stop lap published";
      return multiple ? `${row.route}: ${windows}` : windows;
    }).join(" · ");
  }
  const options = relevantPublishedOptions(baseline, driver);
  const multiple = options.length > 1;
  const summaries = options.map((option) => {
    const driverWindows = driver?.windows?.filter((window) => window.optionId === option.id) ?? [];
    const pending = driverWindows.filter((window) => window.state !== "COMPLETED");
    const values = (pending.length ? pending : driverWindows).map((window) => `L${window.startLap}–${window.endLap}`);
    const fallback = option.pitWindows.filter(Boolean).map((window) => `L${window.startLap}–${window.endLap}`);
    const text = (values.length ? values : fallback).join(", ") || "no lap published";
    return multiple ? `${optionPathText(option)}: ${text}` : text;
  });
  return summaries.join(" · ") || "No stop lap published";
}
