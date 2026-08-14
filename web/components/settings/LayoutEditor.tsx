import {
  ANALYSIS_MODULES,
  applyRacePreset,
  moveAnalysisModule,
  type AnalysisModuleId,
  type ModuleSize,
  type RaceLayoutConfig,
} from "../../domain/layout";

const sizes: ModuleSize[] = ["compact", "standard", "tall"];

export function LayoutEditor({ value, onChange }: { value: RaceLayoutConfig; onChange: (value: RaceLayoutConfig) => void }) {
  const toggle = (id: AnalysisModuleId) => {
    const hiddenModules = value.hiddenModules.includes(id)
      ? value.hiddenModules.filter((item) => item !== id)
      : [...value.hiddenModules, id];
    onChange({ ...value, preset: "custom", hiddenModules });
  };
  const setSize = (id: AnalysisModuleId, size: ModuleSize) => onChange({
    ...value,
    preset: "custom",
    moduleSizes: { ...value.moduleSizes, [id]: size },
  });

  return (
    <div className="settings-page layout-editor">
      <header className="settings-page-heading layout-heading">
        <div><span>MY SETTINGS / LAYOUTS</span><h1>Layout Editor</h1><p>Race modules resolve from Instance default to User preference to this Device override.</p></div>
        <div className="ownership-stack"><span>INSTANCE DEFAULT</span><i /><span>USER PREFERENCE</span><i /><strong>DEVICE OVERRIDE</strong></div>
      </header>
      <section className="layout-preset-section">
        <div><span>RACE SPLIT PRESETS</span><strong>{value.preset.toUpperCase()}</strong></div>
        <div className="layout-editor-presets">
          <button onClick={() => onChange(applyRacePreset(value, "balanced"))}>BALANCED</button>
          <button onClick={() => onChange(applyRacePreset(value, "timing"))}>TIMING FOCUS</button>
          <button onClick={() => onChange(applyRacePreset(value, "strategy"))}>STRATEGY FOCUS</button>
        </div>
        <label><span>TIMING {Math.round(value.timingWidth)}%</span><input type="range" min="48" max="76" value={value.timingWidth} onChange={(event) => onChange({ ...value, preset: "custom", timingWidth: Number(event.target.value) })} /><span>ANALYSIS {Math.round(100 - value.timingWidth)}%</span></label>
      </section>
      <section className="module-editor-list" aria-label="Race analysis modules">
        <header><span>ORDER</span><span>MODULE</span><span>VISIBILITY</span><span>SIZE</span><span>MOVE</span></header>
        {value.analysisOrder.map((id, index) => {
          const module = ANALYSIS_MODULES.find((item) => item.id === id)!;
          const hidden = value.hiddenModules.includes(id);
          return <article key={id} className={hidden ? "module-editor-row hidden" : "module-editor-row"}>
            <b>{String(index + 1).padStart(2, "0")}</b>
            <div><strong>{module.label}</strong><span>{module.description}</span></div>
            <button className="visibility-toggle" aria-pressed={!hidden} onClick={() => toggle(id)}>{hidden ? "HIDDEN" : "SHOWN"}</button>
            <select aria-label={`${module.label} size`} value={value.moduleSizes[id]} onChange={(event) => setSize(id, event.target.value as ModuleSize)}>{sizes.map((size) => <option key={size} value={size}>{size.toUpperCase()}</option>)}</select>
            <div className="move-controls"><button disabled={index === 0} aria-label={`Move ${module.label} up`} onClick={() => onChange(moveAnalysisModule(value, id, -1))}>UP</button><button disabled={index === value.analysisOrder.length - 1} aria-label={`Move ${module.label} down`} onClick={() => onChange(moveAnalysisModule(value, id, 1))}>DOWN</button></div>
          </article>;
        })}
      </section>
      <footer className="settings-truth-note"><strong>DEVICE OVERRIDE ACTIVE</strong><span>Saved in this browser only. User-profile and instance persistence arrive with the control plane.</span></footer>
    </div>
  );
}

