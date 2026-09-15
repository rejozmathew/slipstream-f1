import { useState, type ReactNode } from "react";

import { Conditions } from "../components/analysis/Conditions";
import { RaceControl } from "../components/analysis/RaceControl";
import { SessionStrategySnapshot } from "../components/analysis/SessionStrategySnapshot";
import { PirelliBaseline, RaceNow } from "../components/analysis/PublishedStrategy";
import { TrackMap } from "../components/analysis/TrackMap";
import { SessionSplit } from "../components/shared/SessionSplit";
import { TimingTower } from "../components/timing/TimingTower";
import { applyRacePreset, type AnalysisModuleId, type RaceLayoutConfig, type TowerView } from "../domain/layout";
import type { AnalyticsSnapshot, PositionMode, ViewingMode, RaceState } from "../domain/protocol";

import "./race-session.css";

type RaceViewProps = {
  state: RaceState;
  analytics: AnalyticsSnapshot | null;
  replayAvailable: boolean;
  intervalsAvailable?: boolean;
  positionMode: PositionMode; viewingMode: ViewingMode;
  layout: RaceLayoutConfig;
  onLayoutChange: (layout: RaceLayoutConfig) => void;
  onOpenLayoutEditor: () => void;
  onSelectDriver: (driverNumber: string) => void;
  towerView: TowerView;
  onTowerViewChange: (view: TowerView) => void;
  onOpenStrategy: () => void;
};

export function RaceView({ state, analytics, replayAvailable, intervalsAvailable = false, positionMode, viewingMode, layout, onLayoutChange, onOpenLayoutEditor, onSelectDriver, towerView, onTowerViewChange, onOpenStrategy }: RaceViewProps) {
  const [mobileTab, setMobileTab] = useState<"timing" | "strategy" | "map" | "control">("timing");
  const drivers = Object.values(state.drivers).sort((a, b) => (a.position ?? 999) - (b.position ?? 999));
  const modules: Record<AnalysisModuleId, ReactNode> = {
    strategy: <SessionStrategySnapshot viewingMode={viewingMode} analytics={analytics} onOpenStrategy={onOpenStrategy} compact={layout.moduleSizes.strategy === "compact"} />,
    map: <TrackMap lapInHeader circuit={state.circuit} session={state.session} drivers={drivers} positionMode={positionMode} viewingMode={viewingMode} />,
    conditions: <Conditions weather={state.weather} session={state.session} />,
    raceControl: <RaceControl messages={state.race_control} />,
  };

  return (
    <div className="race-workspace">
      <div className="race-desktop">
      <SessionSplit className="race-split" timingWidth={layout.timingWidth} onTimingWidthChange={(timingWidth) => onLayoutChange({ ...layout, preset: "custom", timingWidth })} timing={<TimingTower drivers={drivers} variant="race" desktopRaceColumns mode={towerView} analytics={analytics} replayAvailable={replayAvailable} intervalsAvailable={intervalsAvailable} onSelectDriver={onSelectDriver} toolbar={<div className="tower-toolbar"><details className="race-layout-menu"><summary>SPLIT · {layout.preset === "custom" ? "CUSTOM" : layout.preset === "towerWide" ? "TOWER WIDE" : layout.preset === "analysisWide" ? "ANALYSIS WIDE" : "BALANCED"}</summary><div className="layout-presets" role="group" aria-label="Race split preset">
          <span>SPLIT</span><button className={layout.preset === "balanced" ? "active" : ""} onClick={() => onLayoutChange(applyRacePreset(layout, "balanced"))}>BALANCED</button><button className={layout.preset === "towerWide" ? "active" : ""} onClick={() => onLayoutChange(applyRacePreset(layout, "towerWide"))}>TOWER WIDE</button><button className={layout.preset === "analysisWide" ? "active" : ""} onClick={() => onLayoutChange(applyRacePreset(layout, "analysisWide"))}>ANALYSIS WIDE</button><button onClick={onOpenLayoutEditor}>EDIT</button>
        </div></details><div className="tower-view-modes" role="group" aria-label="Timing tower view"><span>TOWER VIEW</span>{(["standard", "timing", "strategy"] as const).map((item) => <button className={towerView === item ? "active" : ""} key={item} onClick={() => onTowerViewChange(item)}>{item.toUpperCase()}</button>)}</div></div>} />} analysis={<div className="analysis-stack race-analysis">
          {layout.analysisOrder.filter((id) => !layout.hiddenModules.includes(id)).map((id) => <div className="analysis-module" data-module={id} data-size={layout.moduleSizes[id]} key={id}>{modules[id]}</div>)}
        </div>} />
      </div>
      <div className="mobile-session mobile-race-session">
        <nav className="mobile-priority-tabs" aria-label="Race views">{(["timing", "strategy", "map", "control"] as const).map((tab) => <button className={mobileTab === tab ? "active" : ""} key={tab} onClick={() => setMobileTab(tab)}>{tab.toUpperCase()}</button>)}</nav>
        <div className="mobile-session-content">
          <div className="mobile-primary">
            {mobileTab === "timing" && <TimingTower drivers={drivers} variant="race" analytics={analytics} replayAvailable={replayAvailable} onSelectDriver={onSelectDriver} />}
        {mobileTab === "strategy" && <div className="mobile-strategy-foundation"><PirelliBaseline baseline={analytics?.publishedStrategy?.baseline} compact /><RaceNow analytics={analytics} compact /></div>}
            {mobileTab === "map" && <div className="mobile-map-stack"><TrackMap circuit={state.circuit} session={state.session} drivers={drivers} positionMode={positionMode} viewingMode={viewingMode} /><Conditions weather={state.weather} session={state.session} /></div>}
            {mobileTab === "control" && <RaceControl messages={state.race_control} />}
          </div>
          <div className="landscape-companion">{mobileTab === "control" ? <Conditions weather={state.weather} session={state.session} /> : <TrackMap circuit={state.circuit} session={state.session} drivers={drivers} positionMode={positionMode} viewingMode={viewingMode} />}</div>
        </div>
      </div>
    </div>
  );
}

