import { useState, type ReactNode } from "react";
import type { AnalyticsSnapshot, PositionMode, RaceState, ViewingMode } from "../../domain/protocol";
import { Panel } from "../shared/Panel";
import { Conditions } from "./Conditions";
import { RaceControl } from "./RaceControl";
import { TrackMap } from "./TrackMap";
import { TimedSessionPanel, TimedSessionSummary } from "./NonRaceTVFeature";

export function NonRaceAnalysis({ state, analytics, positionMode, viewingMode, onSelectDriver, story }: { state: RaceState; analytics?: AnalyticsSnapshot | null; positionMode: PositionMode; viewingMode: ViewingMode; onSelectDriver: (number: string) => void; story?: ReactNode }) {
  const [preset, setPreset] = useState<"brief" | "map" | "story">("brief");
  const [mapSize, setMapSize] = useState<"compact" | "standard" | "tall">("standard");
  const qualifying = state.session.layout_family === "qualifying";
  const conditions = <Conditions weather={state.weather} session={state.session} />;
  const control = <RaceControl messages={state.race_control} />;
  return <div className="nonrace-analysis"><header className="analysis-toolbar"><strong>ANALYSIS</strong><div role="group" aria-label="Analysis preset">{(["brief", "map", "story"] as const).map(value => <button key={value} aria-pressed={preset === value} onClick={() => setPreset(value)}>{value.toUpperCase()}</button>)}</div><div role="group" aria-label="Map size"><span>MAP</span>{(["compact", "standard", "tall"] as const).map((value, index) => <button key={value} aria-pressed={mapSize === value} onClick={() => setMapSize(value)}>{["S", "M", "L"][index]}</button>)}</div></header><div className={`nonrace-analysis-grid nr-analysis-${qualifying ? "qualifying" : "practice"}`} data-preset={preset}>
    {qualifying && <><div className="nr-analysis-session"><Panel eyebrow="QUALIFYING" title="Session" className="qualifying-session-panel"><TimedSessionSummary intelligence={analytics?.qualifying?.status === "AVAILABLE" ? analytics.qualifying : null} /></Panel>{conditions}</div><div className="nr-analysis-control">{control}</div></>}
    <div className="nr-analysis-spread"><TimedSessionPanel state={state} analytics={analytics} onSelectDriver={onSelectDriver} /></div>
    <div className="nr-analysis-map" data-size={mapSize}><TrackMap circuit={state.circuit} session={state.session} drivers={Object.values(state.drivers)} positionMode={positionMode} viewingMode={viewingMode} /></div>
    {!qualifying && <div className="nr-analysis-session">{conditions}{control}</div>}
    <div className={`nr-analysis-story${qualifying ? "" : " nr-analysis-story-wide"}`}>{story ?? <Panel title="Story" eyebrow="AT THIS MOMENT"><p className="panel-empty">No story events available at this moment.</p></Panel>}</div>
  </div></div>;
}
