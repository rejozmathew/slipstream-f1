import {
  ACCENT_OPTIONS,
  BACKGROUND_OPTIONS,
  type AppearancePreferences,
} from "../../domain/appearance";

export function AppearanceSettings({ value, onChange }: { value: AppearancePreferences; onChange: (value: AppearancePreferences) => void }) {
  return (
    <div className="settings-page appearance-settings">
      <header className="settings-page-heading">
        <span>MY SETTINGS</span>
        <h1>Appearance</h1>
        <p>Background and accent are independent. Flag, tyre, sector, safety-car, and team colors stay locked.</p>
      </header>
      <section className="settings-section">
        <div className="settings-section-copy"><h2>Background</h2><p>Dark themes only in V1.</p></div>
        <div className="background-options">
          {BACKGROUND_OPTIONS.map((option) => <button
            className={value.background === option.id ? "appearance-option selected" : "appearance-option"}
            key={option.id}
            onClick={() => onChange({ ...value, background: option.id })}
          >
            <i className={`theme-swatch theme-${option.id}`} />
            <span><strong>{option.label}</strong><small>{option.description}</small></span>
            <b>{value.background === option.id ? "SELECTED" : ""}</b>
          </button>)}
        </div>
      </section>
      <section className="settings-section">
        <div className="settings-section-copy"><h2>Accent</h2><p>Used for navigation and interaction, never semantic session state.</p></div>
        <div className="accent-options">
          {ACCENT_OPTIONS.map((option) => <button
            className={value.accent === option.id ? "accent-option selected" : "accent-option"}
            data-accent-option={option.id}
            key={option.id}
            onClick={() => onChange({ ...value, accent: option.id })}
          ><i /><span>{option.label}</span></button>)}
        </div>
      </section>
      <footer className="settings-truth-note"><strong>THIS DEVICE</strong><span>Appearance is stored locally until Viewer Profiles and server persistence are enabled.</span></footer>
    </div>
  );
}

