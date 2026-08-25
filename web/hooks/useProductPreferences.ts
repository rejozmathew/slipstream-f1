import { useEffect, useState } from "react";

import { DEFAULT_APPEARANCE, type AppearancePreferences } from "../domain/appearance";
import { INSTANCE_RACE_LAYOUT, type RaceLayoutConfig, type TowerView } from "../domain/layout";

const STORAGE_KEY = "slipstream.device-preferences.v1";

type StoredPreferences = {
  appearance: AppearancePreferences;
  raceLayout: RaceLayoutConfig;
  towerView: TowerView;
  lastDriverNumber: string | null;
  battle: BattlePreferences;
  tv: TVPreferences;
};

export type BattlePreferences = {
  mode: "recommended" | "leader" | "pinned";
  pinnedPair: [string, string];
};

export type TVStatePreference = "tower" | "track" | "strategy" | "battle" | "driver";
export type TVPreferences = {
  includedRaceStates: TVStatePreference[];
  selectedDriverNumber: string | null;
  battleMode: "recommended" | "leader" | "pinned";
  pinnedBattle: [string, string];
  rotationIntervalSeconds: number;
  alertOnCriticalStatus: boolean;
};

export const DEFAULT_TV_PREFERENCES: TVPreferences = {
  includedRaceStates: ["tower", "track", "strategy", "battle", "driver"],
  selectedDriverNumber: null,
  battleMode: "recommended",
  pinnedBattle: ["", ""],
  rotationIntervalSeconds: 12,
  alertOnCriticalStatus: true,
};

const DEFAULT_BATTLE_PREFERENCES: BattlePreferences = {
  mode: "recommended",
  pinnedPair: ["", ""],
};

const defaults = (): StoredPreferences => ({
  appearance: DEFAULT_APPEARANCE,
  raceLayout: INSTANCE_RACE_LAYOUT,
  towerView: "standard",
  lastDriverNumber: null,
  battle: DEFAULT_BATTLE_PREFERENCES,
  tv: DEFAULT_TV_PREFERENCES,
});

function readDevicePreferences(): StoredPreferences {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (!stored) return defaults();
    const parsed = JSON.parse(stored) as Partial<StoredPreferences>;
    const legacyPreset = parsed.raceLayout?.preset as string | undefined;
    const raceLayout = {
      ...INSTANCE_RACE_LAYOUT,
      ...parsed.raceLayout,
      preset: legacyPreset === "timing" ? "towerWide" : legacyPreset === "strategy" ? "analysisWide" : parsed.raceLayout?.preset ?? INSTANCE_RACE_LAYOUT.preset,
      moduleSizes: { ...INSTANCE_RACE_LAYOUT.moduleSizes, ...parsed.raceLayout?.moduleSizes },
    } as RaceLayoutConfig;
    return {
      appearance: { ...DEFAULT_APPEARANCE, ...parsed.appearance },
      raceLayout,
      towerView: parsed.towerView ?? "standard",
      lastDriverNumber: parsed.lastDriverNumber ?? null,
      battle: { ...DEFAULT_BATTLE_PREFERENCES, ...parsed.battle },
      tv: { ...DEFAULT_TV_PREFERENCES, ...parsed.tv },
    };
  } catch {
    return defaults();
  }
}

export function useProductPreferences() {
  const [initial] = useState(readDevicePreferences);
  const [appearance, setAppearance] = useState<AppearancePreferences>(initial.appearance);
  const [raceLayout, setRaceLayout] = useState<RaceLayoutConfig>(initial.raceLayout);
  const [towerView, setTowerView] = useState<TowerView>(initial.towerView);
  const [lastDriverNumber, setLastDriverNumber] = useState<string | null>(initial.lastDriverNumber);
  const [battle, setBattle] = useState<BattlePreferences>(initial.battle);
  const [tv, setTV] = useState<TVPreferences>(initial.tv);

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ appearance, raceLayout, towerView, lastDriverNumber, battle, tv }));
    } catch {
      // Storage can be disabled; preferences still work for this page lifetime.
    }
  }, [appearance, battle, lastDriverNumber, raceLayout, towerView, tv]);

  return { appearance, setAppearance, raceLayout, setRaceLayout, towerView, setTowerView, lastDriverNumber, setLastDriverNumber, battle, setBattle, tv, setTV };
}
