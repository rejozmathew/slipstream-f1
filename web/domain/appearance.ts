export type BackgroundTheme = "flat-dark" | "midnight-gradient" | "graphite-gradient";
export type AccentColor = "cyan" | "papaya" | "red" | "blue" | "purple" | "green";

export type MotionPreference = "system" | "full" | "reduced";
export type DisplaySize = 75 | 80 | 90 | 100;

export type AppearancePreferences = {
  background: BackgroundTheme;
  accent: AccentColor;
  displaySize?: DisplaySize;
  motion?: MotionPreference;
};

export const DEFAULT_APPEARANCE: AppearancePreferences = {
  background: "flat-dark",
  accent: "red",
  displaySize: 80,
  motion: "system",
};

export const BACKGROUND_OPTIONS: Array<{ id: BackgroundTheme; label: string; description: string }> = [
  { id: "flat-dark", label: "Flat Dark", description: "Near-black technical surface" },
  { id: "midnight-gradient", label: "Midnight Gradient", description: "Navy fading to near-black" },
  { id: "graphite-gradient", label: "Graphite Gradient", description: "Neutral charcoal depth" },
];

export const ACCENT_OPTIONS: Array<{ id: AccentColor; label: string }> = [
  { id: "cyan", label: "Cyan" },
  { id: "papaya", label: "Papaya" },
  { id: "red", label: "Red" },
  { id: "blue", label: "Blue" },
  { id: "purple", label: "Purple" },
  { id: "green", label: "Green" },
];

