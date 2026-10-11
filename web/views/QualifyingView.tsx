import { useState, type ReactNode } from "react";

import { Conditions } from "../components/analysis/Conditions";
import { NonRaceAnalysis } from "../components/analysis/NonRaceAnalysis";
import { AroundCut, OnTrackNow, TimedSessionSummary } from "../components/analysis/NonRaceTVFeature";
import { RaceControl } from "../components/analysis/RaceControl";
import { TrackMap } from "../components/analysis/TrackMap";
import { Panel } from "../components/shared/Panel";
import { SessionSplit } from "../components/shared/SessionSplit";
import { PhoneTimingTower } from "../components/timing/PhoneTimingTower";
import { TimingTower } from "../components/timing/TimingTower";
import type { QualifyingTowerView } from "../domain/layout";
import type { AnalyticsSnapshot, PositionMode, ViewingMode, QualifyingIntelligence, RaceState, SessionKind } from "../domain/protocol";

export function SessionPanel({ intelligence }: { intelligence: QualifyingIntelligence | null }) {
  return <Panel eyebrow="QUALIFYING" title="SESSION" className="qualifying-session-panel"><TimedSessionSummary intelligence={intelligence} /></Panel>;
}

export function QualifyingView({ timingWidth = 66, onTimingWidthChange = () => {}, state, analytics, replayAvailable, timingNotice, positionMode, viewingMode, sectorTimingAvailable, onSelectDriver, towerView, onTowerViewChange, story }: { story?: ReactNode; timingWidth?: number; onTimingWidthChange?: (width: number) => void; towerView: QualifyingTowerView; onTowerViewChange: (mode: QualifyingTowerView) => void; state: RaceState; analytics: AnalyticsSnapshot | null; sessionKind: SessionKind; replayAvailable: boolean; timingNotice?: ReactNode; positionMode: PositionMode; viewingMode: ViewingMode; sectorTimingAvailable: boolean; onSelectDriver: (driverNumber: string) => void }) {
  const [mobileTab, setMobileTab] = useState<"timing" | "session" | "track" | "control">("timing");
  const drivers = Object.values(state.drivers).sort((a, b) => (a.position ?? 999) - (b.position ?? 999));
  const intelligence = analytics?.qualifying?.status === "AVAILABLE" ? analytics.qualifying : null;
  const session = <SessionPanel intelligence={intelligence} />;
  const tabs = ["timing", "session", "track", "control"] as const;
  const toolbar = <div className="tower-view-modes qualifying-view-modes" role="group" aria-label="Qualifying timing tower view"><span>TOWER VIEW</span>{(["standard", "timing"] as const).map((mode) => <button type="button" key={mode} className={towerView === mode ? "active" : ""} aria-pressed={towerView === mode} onClick={() => onTowerViewChange(mode)}>{mode.toUpperCase()}</button>)}</div>;
  return <><SessionSplit className="session-layout qualifying-layout session-desktop" timingWidth={timingWidth} onTimingWidthChange={onTimingWidthChange} timing={<TimingTower drivers={drivers} variant="qualifying" mode={towerView} toolbar={toolbar} analytics={analytics} replayAvailable={replayAvailable} timingNotice={timingNotice} sectorTimingAvailable={sectorTimingAvailable} onSelectDriver={onSelectDriver} />} analysis={<NonRaceAnalysis state={state} analytics={analytics} positionMode={positionMode} viewingMode={viewingMode} onSelectDriver={onSelectDriver} story={story} />} />
    <div className="mobile-session mobile-qualifying-session"><nav className="mobile-priority-tabs" aria-label="Qualifying views">{tabs.map((tab) => <button className={mobileTab === tab ? "active" : ""} key={tab} onClick={() => setMobileTab(tab)}>{({ timing: "TIMING", session: "CUT LINE", track: "TRACK", control: "ACTIVITY" })[tab]}</button>)}</nav><div className="mobile-session-content"><div className="mobile-primary">{mobileTab === "timing" ? <div className="phone-timing-with-detail"><PhoneTimingTower drivers={drivers} variant="qualifying" analytics={analytics} replayAvailable={replayAvailable} timingNotice={timingNotice} onSelectDriver={onSelectDriver} /><details className="phone-full-timing"><summary>FULL TIMING TABLE</summary><TimingTower drivers={drivers} variant="qualifying" mode={towerView} toolbar={toolbar} analytics={analytics} replayAvailable={replayAvailable} timingNotice={timingNotice} sectorTimingAvailable={sectorTimingAvailable} onSelectDriver={onSelectDriver} /></details></div> : mobileTab === "session" ? <div className="phone-timed-session">{session}<Panel title="Around the cut" eyebrow={intelligence?.phase === "UNKNOWN" ? "SEGMENT UNKNOWN" : intelligence?.phase ?? "QUALIFYING"}><AroundCut state={state} analytics={analytics} onSelectDriver={onSelectDriver} phone /></Panel><Panel title="On track" eyebrow="RUNNING NOW"><OnTrackNow state={state} analytics={analytics} onSelectDriver={onSelectDriver} /></Panel><Conditions weather={state.weather} session={state.session} /></div> : mobileTab === "track" ? <div className="mobile-map-stack"><TrackMap circuit={state.circuit} session={state.session} drivers={drivers} positionMode={positionMode} viewingMode={viewingMode} /><Conditions weather={state.weather} session={state.session} /></div> : <div className="phone-activity">{story}<RaceControl messages={state.race_control} /></div>}</div><div className="landscape-companion">{mobileTab === "timing" ? <TrackMap circuit={state.circuit} session={state.session} drivers={drivers} positionMode={positionMode} viewingMode={viewingMode} /> : <PhoneTimingTower drivers={drivers} variant="qualifying" analytics={analytics} replayAvailable={replayAvailable} timingNotice={timingNotice} onSelectDriver={onSelectDriver} />}</div></div></div></>;
}
