import type { Driver } from "../../domain/protocol";
import type { TVPreferences, TVStatePreference } from "../../hooks/useProductPreferences";

const tvStates: Array<{ id: TVStatePreference; label: string }> = [
  { id: "tower", label: "Timing Tower" },
  { id: "track", label: "Track" },
  { id: "strategy", label: "Strategy" },
  { id: "battle", label: "Battle" },
  { id: "driver", label: "Driver" },
];

export function TVPreferencesSettings({ value, onChange, drivers }: { value: TVPreferences; onChange: (value: TVPreferences) => void; drivers: Driver[] }) {
  const toggleState = (id: TVStatePreference) => {
    const includedRaceStates = value.includedRaceStates.includes(id) ? value.includedRaceStates.filter((item) => item !== id) : [...value.includedRaceStates, id];
    onChange({ ...value, includedRaceStates });
  };
  return <div className="settings-page tv-preferences-settings">
    <header className="settings-page-heading"><span>MY SETTINGS / PREFERENCES</span><h1>TV Mode</h1><p>These presentation choices are stored only on this device.</p></header>
    <section className="settings-section tv-preference-grid">
      <div className="preference-card"><span>RACE ROTATION</span><strong>Included states</strong><div className="tv-state-options">{tvStates.map((item) => <label key={item.id}><input type="checkbox" checked={value.includedRaceStates.includes(item.id)} onChange={() => toggleState(item.id)} /><span>{item.label}</span></label>)}</div></div>
      <div className="preference-card"><span>DRIVER TV</span><strong>Selected driver</strong><select value={value.selectedDriverNumber ?? ""} onChange={(event) => onChange({ ...value, selectedDriverNumber: event.target.value || null })}><option value="">AUTO · LEADER</option>{drivers.map((driver) => <option value={driver.number} key={driver.number}>P{driver.position ?? "—"} · {driver.code ?? driver.number}</option>)}</select></div>
      <div className="preference-card"><span>BATTLE TV</span><strong>Pair mode</strong><select value={value.battleMode} onChange={(event) => onChange({ ...value, battleMode: event.target.value as TVPreferences["battleMode"] })}><option value="recommended">RECOMMENDED</option><option value="leader">LEADER · P1 vs P2</option><option value="pinned">PINNED</option></select>{value.battleMode === "pinned" && <div className="pinned-pair"><select value={value.pinnedBattle[0]} onChange={(event) => onChange({ ...value, pinnedBattle: [event.target.value, value.pinnedBattle[1]] })}><option value="">DRIVER A</option>{drivers.map((driver) => <option value={driver.number} key={driver.number}>{driver.code ?? driver.number}</option>)}</select><select value={value.pinnedBattle[1]} onChange={(event) => onChange({ ...value, pinnedBattle: [value.pinnedBattle[0], event.target.value] })}><option value="">DRIVER B</option>{drivers.map((driver) => <option value={driver.number} key={driver.number}>{driver.code ?? driver.number}</option>)}</select></div>}</div>
      <div className="preference-card"><span>AUTO ROTATION</span><strong>{value.rotationIntervalSeconds} seconds</strong><input type="range" min="5" max="60" step="1" value={value.rotationIntervalSeconds} onChange={(event) => onChange({ ...value, rotationIntervalSeconds: Number(event.target.value) })} /></div>
      <label className="preference-card alert-preference"><input aria-label="Enable critical race-control interrupts" type="checkbox" checked={value.alertOnCriticalStatus} onChange={(event) => onChange({ ...value, alertOnCriticalStatus: event.target.checked })} /><span><b>Critical race-control interrupt</b><small>Briefly expands Yellow, SC, VSC, and Red status changes; persistent status remains visible.</small></span></label>
    </section>
  </div>;
}
