import { ACCENT_OPTIONS, BACKGROUND_OPTIONS, type DisplaySize, type MotionPreference, type AppearancePreferences } from "../../domain/appearance";
import { CompoundBadge } from "../shared/CompoundBadge";

export function AppearanceSettings({ value, onChange }: { value: AppearancePreferences; onChange: (value: AppearancePreferences) => void }) {
  return <div className="settings-page appearance-settings">
    <header className="settings-page-heading"><span>MY SETTINGS</span><h1>Appearance</h1><p>Background and accent are independent. Flag, tyre, sector, safety-car, and team colors stay locked.</p></header>
    <section className="settings-section">
      <div className="settings-section-copy"><h2>Background</h2><p>Dark themes only in V1.</p></div>
      <div className="background-options">{BACKGROUND_OPTIONS.map((option) => <button className={value.background === option.id ? "appearance-option selected" : "appearance-option"} key={option.id} onClick={() => onChange({ ...value, background: option.id })}>
        <i className={`theme-swatch theme-${option.id}`} /><span><strong>{option.label}</strong><small>{option.description}</small></span><b>{value.background === option.id ? "SELECTED" : ""}</b>
      </button>)}</div>
    </section>
    <section className="settings-section">
      <div className="settings-section-copy"><h2>Accent</h2><p>Used for navigation and interaction, never semantic session state.</p></div>
      <div className="accent-options">{ACCENT_OPTIONS.map((option) => <button className={value.accent === option.id ? "accent-option selected" : "accent-option"} data-accent-option={option.id} key={option.id} onClick={() => onChange({ ...value, accent: option.id })}><i /><span>{option.label}</span></button>)}</div>
    </section>
    <section className="settings-section">
      <div className="settings-section-copy"><h2>Display size</h2><p>Adjust desktop type and spacing. Phone controls keep their touch target sizes.</p></div>
      <div className="display-size-options" role="group" aria-label="Display size">{([75, 80, 90, 100] as DisplaySize[]).map((size) => <button key={size} aria-pressed={(value.displaySize ?? 80) === size} onClick={() => onChange({ ...value, displaySize: size })}>{size}%{size === 80 ? " · DEFAULT" : ""}</button>)}</div>
    </section>
    <section className="settings-section">
      <div className="settings-section-copy"><h2>Motion</h2><p>Reduced motion keeps every fact visible without movement or flashing.</p></div>
      <div className="display-size-options" role="group" aria-label="Motion preference">{(["system", "full", "reduced"] as MotionPreference[]).map((motion) => <button key={motion} aria-pressed={(value.motion ?? "system") === motion} onClick={() => onChange({ ...value, motion })}>{motion.toUpperCase()}</button>)}</div>
    </section>
    <section className="settings-section appearance-live-preview">
      <div className="settings-section-copy"><h2>Live preview</h2><p>Representative panel, timing value, tyre and control surfaces.</p></div>
      <div className="appearance-preview-card" data-preview-background={value.background}>
        <header><span>RACE CONTROL</span><b>GREEN TRACK</b></header>
        <div><strong>P4</strong><span><b>NOR</b><small>McLaren</small></span><em>+1.284</em><CompoundBadge compound="MEDIUM" compact /><button>FOCUS</button></div>
      </div>
    </section>
    <footer className="settings-truth-note"><strong>THIS DEVICE</strong><span>Appearance is stored locally until Viewer Profiles and server persistence are enabled.</span></footer>
  </div>;
}
