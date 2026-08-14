export type BackgroundTheme = "flat-dark" | "midnight-gradient" | "graphite-gradient";
export type AccentColor = "cyan" | "papaya" | "red" | "blue" | "purple" | "green";

export type AppearancePreferences = {
  background: BackgroundTheme;
  accent: AccentColor;
};

export const DEFAULT_APPEARANCE: AppearancePreferences = {
  background: "midnight-gradient",
  accent: "cyan",
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

