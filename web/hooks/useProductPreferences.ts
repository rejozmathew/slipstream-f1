import { useEffect, useState } from "react";

import { DEFAULT_APPEARANCE, type AppearancePreferences } from "../domain/appearance";
import { INSTANCE_RACE_LAYOUT, type RaceLayoutConfig, type TowerView, type QualifyingTowerView } from "../domain/layout";

const STORAGE_KEY = "slipstream.device-preferences.v1";

type StoredPreferences = {
  appearance: AppearancePreferences;
  raceLayout: RaceLayoutConfig;
  towerView: TowerView;
  qualifyingTowerView: QualifyingTowerView;
  sessionWidths: { qualifying: number; practice: number };
  lastDriverNumber: string | null;
  battle: BattlePreferences;
  tv: TVPreferences;
};

export type BattlePreferences = {
  mode: "recommended" | "leader" | "pinned";
  pinnedPair: [string, string];
};

export type TVStatePreference = "tower" | "track" | "strategy" | "battle" | "driver" | "result";
export type TVPreferences = {
  includedRaceStates: TVStatePreference[];
  selectedDriverNumber: string | null;
  battleMode: "recommended" | "leader" | "pinned";
  pinnedBattle: [string, string];
  rotationIntervalSeconds: number;
  alertOnCriticalStatus: boolean;
  textSize?: number;
  safeArea?: number;
};

export const DEFAULT_TV_PREFERENCES: TVPreferences = {
  includedRaceStates: ["track", "strategy", "battle", "driver", "result"],
  selectedDriverNumber: null,
  battleMode: "recommended",
  pinnedBattle: ["", ""],
  rotationIntervalSeconds: 12,
  alertOnCriticalStatus: true,
  textSize: 1,
  safeArea: 0,
};

const DEFAULT_BATTLE_PREFERENCES: BattlePreferences = {
  mode: "recommended",
  pinnedPair: ["", ""],
};

const defaults = (): StoredPreferences => ({
  appearance: DEFAULT_APPEARANCE,
  raceLayout: INSTANCE_RACE_LAYOUT,
  towerView: "standard",
  qualifyingTowerView: "standard",
  sessionWidths: { qualifying: 56, practice: 56 },
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
      analysisOrder: parsed.raceLayout?.analysisOrder ? [...parsed.raceLayout.analysisOrder, ...INSTANCE_RACE_LAYOUT.analysisOrder.filter((id) => !parsed.raceLayout?.analysisOrder?.includes(id))] : INSTANCE_RACE_LAYOUT.analysisOrder,
    } as RaceLayoutConfig;
    return {
      appearance: { ...DEFAULT_APPEARANCE, ...parsed.appearance },
      raceLayout,
      towerView: parsed.towerView ?? "standard",
      qualifyingTowerView: parsed.qualifyingTowerView === "timing" ? "timing" : "standard",
      sessionWidths: {
        qualifying: typeof parsed.sessionWidths?.qualifying === "number" && Number.isFinite(parsed.sessionWidths.qualifying) ? parsed.sessionWidths.qualifying : 66,
        practice: typeof parsed.sessionWidths?.practice === "number" && Number.isFinite(parsed.sessionWidths.practice) ? parsed.sessionWidths.practice : 66,
      },
      lastDriverNumber: parsed.lastDriverNumber ?? null,
      battle: parsed.battle ? { ...DEFAULT_BATTLE_PREFERENCES, ...parsed.battle } : { mode: parsed.tv?.battleMode ?? DEFAULT_BATTLE_PREFERENCES.mode, pinnedPair: parsed.tv?.pinnedBattle ?? DEFAULT_BATTLE_PREFERENCES.pinnedPair },
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
  const [qualifyingTowerView, setQualifyingTowerView] = useState<QualifyingTowerView>(initial.qualifyingTowerView);
  const [sessionWidths, setSessionWidths] = useState(initial.sessionWidths);
  const [lastDriverNumber, setLastDriverNumber] = useState<string | null>(initial.lastDriverNumber);
  const [battle, setBattle] = useState<BattlePreferences>(initial.battle);
  const [tv, setTVState] = useState<TVPreferences>(initial.tv);
  // One viewer owns its pinned pair; TV only changes presentation of that pair.
  const viewerTV = { ...tv, battleMode: battle.mode, pinnedBattle: battle.pinnedPair };
  const setTV = (value: TVPreferences) => {
    setTVState(value);
    setBattle({ mode: value.battleMode, pinnedPair: value.pinnedBattle });
  };

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ appearance, raceLayout, towerView, qualifyingTowerView, sessionWidths, lastDriverNumber, battle, tv: { ...tv, battleMode: battle.mode, pinnedBattle: battle.pinnedPair } }));
    } catch {
      // Storage can be disabled; preferences still work for this page lifetime.
    }
  }, [appearance, battle, lastDriverNumber, raceLayout, towerView, qualifyingTowerView, sessionWidths, tv]);

  return { appearance, setAppearance, raceLayout, setRaceLayout, towerView, setTowerView, qualifyingTowerView, setQualifyingTowerView, sessionWidths, setSessionWidths, lastDriverNumber, setLastDriverNumber, battle, setBattle, tv: viewerTV, setTV };
}
