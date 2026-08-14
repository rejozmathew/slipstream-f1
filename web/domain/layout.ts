export type LayoutOwner = "instance" | "user" | "device";
export type AnalysisModuleId = "strategy" | "map" | "conditions" | "raceControl";
export type ModuleSize = "compact" | "standard" | "tall";
export type RacePresetId = "balanced" | "timing" | "strategy" | "custom";

export type RaceLayoutConfig = {
  timingWidth: number;
  preset: RacePresetId;
  analysisOrder: AnalysisModuleId[];
  hiddenModules: AnalysisModuleId[];
  moduleSizes: Record<AnalysisModuleId, ModuleSize>;
};

export type LayoutLayer = {
  owner: LayoutOwner;
  race?: Partial<RaceLayoutConfig>;
};

export const ANALYSIS_MODULES: Array<{ id: AnalysisModuleId; label: string; description: string }> = [
  { id: "strategy", label: "Strategy Outlook", description: "Production analytics when enabled" },
  { id: "map", label: "Track Map", description: "Circuit shape and factual car position" },
  { id: "conditions", label: "Conditions", description: "Weather and track-local context" },
  { id: "raceControl", label: "Race Control", description: "Flags, notices, and control messages" },
];

export const RACE_PRESETS: Record<Exclude<RacePresetId, "custom">, number> = {
  balanced: 66,
  timing: 76,
  strategy: 56,
};

export const INSTANCE_RACE_LAYOUT: RaceLayoutConfig = {
  timingWidth: RACE_PRESETS.balanced,
  preset: "balanced",
  analysisOrder: ["strategy", "map", "conditions", "raceControl"],
  hiddenModules: [],
  moduleSizes: {
    strategy: "compact",
    map: "tall",
    conditions: "standard",
    raceControl: "standard",
  },
};

export function resolveRaceLayout(layers: LayoutLayer[]): RaceLayoutConfig {
  return layers.reduce<RaceLayoutConfig>((resolved, layer) => {
    if (!layer.race) return resolved;
    return {
      ...resolved,
      ...layer.race,
      analysisOrder: layer.race.analysisOrder ?? resolved.analysisOrder,
      hiddenModules: layer.race.hiddenModules ?? resolved.hiddenModules,
      moduleSizes: { ...resolved.moduleSizes, ...layer.race.moduleSizes },
    };
  }, INSTANCE_RACE_LAYOUT);
}

export function applyRacePreset(layout: RaceLayoutConfig, preset: Exclude<RacePresetId, "custom">): RaceLayoutConfig {
  return { ...layout, preset, timingWidth: RACE_PRESETS[preset] };
}

export function moveAnalysisModule(layout: RaceLayoutConfig, id: AnalysisModuleId, direction: -1 | 1): RaceLayoutConfig {
  const current = layout.analysisOrder.indexOf(id);
  const next = current + direction;
  if (current < 0 || next < 0 || next >= layout.analysisOrder.length) return layout;
  const analysisOrder = [...layout.analysisOrder];
  [analysisOrder[current], analysisOrder[next]] = [analysisOrder[next], analysisOrder[current]];
  return { ...layout, preset: "custom", analysisOrder };
}

