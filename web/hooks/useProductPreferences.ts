import { useEffect, useState } from "react";

import { DEFAULT_APPEARANCE, type AppearancePreferences } from "../domain/appearance";
import { INSTANCE_RACE_LAYOUT, type RaceLayoutConfig } from "../domain/layout";

const STORAGE_KEY = "slipstream.device-preferences.v1";

type StoredPreferences = {
  appearance: AppearancePreferences;
  raceLayout: RaceLayoutConfig;
};

function readDevicePreferences(): StoredPreferences {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (!stored) return { appearance: DEFAULT_APPEARANCE, raceLayout: INSTANCE_RACE_LAYOUT };
    const parsed = JSON.parse(stored) as Partial<StoredPreferences>;
    return {
      appearance: { ...DEFAULT_APPEARANCE, ...parsed.appearance },
      raceLayout: {
        ...INSTANCE_RACE_LAYOUT,
        ...parsed.raceLayout,
        moduleSizes: { ...INSTANCE_RACE_LAYOUT.moduleSizes, ...parsed.raceLayout?.moduleSizes },
      },
    };
  } catch {
    return { appearance: DEFAULT_APPEARANCE, raceLayout: INSTANCE_RACE_LAYOUT };
  }
}

export function useProductPreferences() {
  const [initial] = useState(readDevicePreferences);
  const [appearance, setAppearance] = useState<AppearancePreferences>(initial.appearance);
  const [raceLayout, setRaceLayout] = useState<RaceLayoutConfig>(initial.raceLayout);

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ appearance, raceLayout }));
    } catch {
      // Storage can be disabled; preferences still work for this page lifetime.
    }
  }, [appearance, raceLayout]);

  return { appearance, setAppearance, raceLayout, setRaceLayout };
}
