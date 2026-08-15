import { AppearanceSettings } from "../components/settings/AppearanceSettings";
import { LayoutEditor } from "../components/settings/LayoutEditor";
import { TVPreferencesSettings } from "../components/settings/TVPreferencesSettings";
import type { AppearancePreferences } from "../domain/appearance";
import type { Driver } from "../domain/protocol";
import type { RaceLayoutConfig } from "../domain/layout";
import type { TVPreferences } from "../hooks/useProductPreferences";

export type SettingsSection = "profile" | "appearance" | "layouts" | "sync" | "preferences";

const sections: Array<{ id: SettingsSection; label: string; detail: string }> = [
  { id: "profile", label: "Profile", detail: "Identity and sessions" },
  { id: "appearance", label: "Appearance", detail: "Theme and accent" },
  { id: "layouts", label: "Layouts", detail: "Presets and modules" },
  { id: "sync", label: "Sync & Devices", detail: "Groups and displays" },
  { id: "preferences", label: "Preferences", detail: "Viewer defaults" },
];

function PendingSettings({ section }: { section: SettingsSection }) {
  const copy = {
    profile: ["Profile", "Viewer Profile credentials and remembered sessions will be managed here after authentication is enabled."],
    sync: ["Sync & Devices", "Sync Groups, dedicated displays, and expiring device pairing require the later control-plane backend."],
    preferences: ["Preferences", "Device-local TV and presentation defaults."],
    appearance: ["Appearance", ""],
    layouts: ["Layouts", ""],
  }[section];
  return <div className="settings-page"><header className="settings-page-heading"><span>MY SETTINGS</span><h1>{copy[0]}</h1><p>{copy[1]}</p></header><section className="not-configured-card"><span>BACKEND STATUS</span><strong>NOT CONFIGURED</strong><p>The production page structure is ready; unavailable controls remain disabled until their required backend exists.</p><button disabled>MANAGE {copy[0].toUpperCase()}</button></section></div>;
}

export function SettingsView({ appearance, onAppearanceChange, raceLayout, onRaceLayoutChange, tvPreferences, onTVPreferencesChange, drivers, section, onSectionChange }: {
  appearance: AppearancePreferences;
  onAppearanceChange: (value: AppearancePreferences) => void;
  raceLayout: RaceLayoutConfig;
  onRaceLayoutChange: (value: RaceLayoutConfig) => void;
  tvPreferences: TVPreferences;
  onTVPreferencesChange: (value: TVPreferences) => void;
  drivers: Driver[];
  section: SettingsSection;
  onSectionChange: (section: SettingsSection) => void;
}) {
  return <div className="settings-shell">
    <aside className="settings-nav"><header><span>ACCOUNT</span><strong>My Settings</strong></header>{sections.map((item) => <button key={item.id} className={section === item.id ? "active" : ""} onClick={() => onSectionChange(item.id)}><strong>{item.label}</strong><span>{item.detail}</span></button>)}</aside>
    <div className="settings-content">{section === "appearance" ? <AppearanceSettings value={appearance} onChange={onAppearanceChange} /> : section === "layouts" ? <LayoutEditor value={raceLayout} onChange={onRaceLayoutChange} /> : section === "preferences" ? <TVPreferencesSettings value={tvPreferences} onChange={onTVPreferencesChange} drivers={drivers} /> : <PendingSettings section={section} />}</div>
  </div>;
}
