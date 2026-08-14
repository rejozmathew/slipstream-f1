import { useState, type PointerEvent as ReactPointerEvent, type ReactNode } from "react";

import { Conditions } from "../components/analysis/Conditions";
import { RaceControl } from "../components/analysis/RaceControl";
import { StrategyOutlook } from "../components/analysis/StrategyOutlook";
import { TrackMap } from "../components/analysis/TrackMap";
import { TimingTower } from "../components/timing/TimingTower";
import { applyRacePreset, type AnalysisModuleId, type RaceLayoutConfig } from "../domain/layout";
import type { PositionMode, RaceState } from "../domain/protocol";

type RaceViewProps = {
  state: RaceState;
  replayAvailable: boolean;
  positionMode: PositionMode;
  layout: RaceLayoutConfig;
  onLayoutChange: (layout: RaceLayoutConfig) => void;
  onOpenLayoutEditor: () => void;
  onSelectDriver: (driverNumber: string) => void;
};

export function RaceView({ state, replayAvailable, positionMode, layout, onLayoutChange, onOpenLayoutEditor, onSelectDriver }: RaceViewProps) {
  const [mobileTab, setMobileTab] = useState<"timing" | "strategy" | "map" | "control">("timing");
  const drivers = Object.values(state.drivers).sort((a, b) => (a.position ?? 999) - (b.position ?? 999));
  const modules: Record<AnalysisModuleId, ReactNode> = {
    strategy: <StrategyOutlook compact={layout.moduleSizes.strategy === "compact"} />,
    map: <TrackMap circuit={state.circuit} session={state.session} drivers={drivers} positionMode={positionMode} />,
    conditions: <Conditions weather={state.weather} session={state.session} />,
    raceControl: <RaceControl messages={state.race_control} />,
  };
  const startDrag = (event: ReactPointerEvent<HTMLButtonElement>) => {
    event.preventDefault();
    const container = event.currentTarget.parentElement;
    if (!container) return;
    const move = (pointer: PointerEvent) => {
      const bounds = container.getBoundingClientRect();
      const next = ((pointer.clientX - bounds.left) / bounds.width) * 100;
      onLayoutChange({ ...layout, preset: "custom", timingWidth: Math.min(76, Math.max(48, next)) });
    };
    const stop = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop, { once: true });
  };

  return (
    <div className="race-workspace">
      <div className="race-desktop">
      <div className="race-split" style={{ gridTemplateColumns: `minmax(0, ${layout.timingWidth}fr) 9px minmax(410px, ${100 - layout.timingWidth}fr)` }}>
        <TimingTower drivers={drivers} variant="race" replayAvailable={replayAvailable} onSelectDriver={onSelectDriver} toolbar={<div className="layout-presets" role="group" aria-label="Race layout preset">
          <span>SPLIT</span><button className={layout.preset === "balanced" ? "active" : ""} onClick={() => onLayoutChange(applyRacePreset(layout, "balanced"))}>BALANCED</button><button className={layout.preset === "timing" ? "active" : ""} onClick={() => onLayoutChange(applyRacePreset(layout, "timing"))}>TIMING FOCUS</button><button className={layout.preset === "strategy" ? "active" : ""} onClick={() => onLayoutChange(applyRacePreset(layout, "strategy"))}>STRATEGY FOCUS</button><button onClick={onOpenLayoutEditor}>EDIT</button>
        </div>} />
        <button className="split-handle" onPointerDown={startDrag} aria-label="Resize timing and analysis panels"><span /></button>
        <div className="analysis-stack race-analysis">
          {layout.analysisOrder.filter((id) => !layout.hiddenModules.includes(id)).map((id) => <div className="analysis-module" data-size={layout.moduleSizes[id]} key={id}>{modules[id]}</div>)}
        </div>
      </div>
      </div>
      <div className="mobile-session mobile-race-session">
        <nav className="mobile-priority-tabs" aria-label="Race views">{(["timing", "strategy", "map", "control"] as const).map((tab) => <button className={mobileTab === tab ? "active" : ""} key={tab} onClick={() => setMobileTab(tab)}>{tab.toUpperCase()}</button>)}</nav>
        <div className="mobile-session-content">
          <div className="mobile-primary">
            {mobileTab === "timing" && <TimingTower drivers={drivers} variant="race" replayAvailable={replayAvailable} onSelectDriver={onSelectDriver} />}
            {mobileTab === "strategy" && <StrategyOutlook />}
            {mobileTab === "map" && <div className="mobile-map-stack"><TrackMap circuit={state.circuit} session={state.session} drivers={drivers} positionMode={positionMode} /><Conditions weather={state.weather} session={state.session} /></div>}
            {mobileTab === "control" && <RaceControl messages={state.race_control} />}
          </div>
          <div className="landscape-companion">{mobileTab === "control" ? <Conditions weather={state.weather} session={state.session} /> : <TrackMap circuit={state.circuit} session={state.session} drivers={drivers} positionMode={positionMode} />}</div>
        </div>
      </div>
    </div>
  );
}
