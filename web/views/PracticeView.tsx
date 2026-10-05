import { useState, type ReactNode } from "react";

import { Conditions } from "../components/analysis/Conditions";
import { RaceControl } from "../components/analysis/RaceControl";
import { TrackMap } from "../components/analysis/TrackMap";
import { SessionSplit } from "../components/shared/SessionSplit";
import { PhoneTimingTower } from "../components/timing/PhoneTimingTower";
import { TimingTower } from "../components/timing/TimingTower";
import type { AnalyticsSnapshot, PositionMode, ViewingMode, RaceState } from "../domain/protocol";

export function PracticeView({ timingWidth = 66, onTimingWidthChange = () => {}, state, analytics, replayAvailable, positionMode, viewingMode, onSelectDriver, story }: { story?: ReactNode; timingWidth?: number; onTimingWidthChange?: (width: number) => void; state: RaceState; analytics?: AnalyticsSnapshot | null; replayAvailable: boolean; positionMode: PositionMode; viewingMode: ViewingMode; onSelectDriver: (driverNumber: string) => void }) {
  const [mobileTab, setMobileTab] = useState<"timing" | "track" | "runs" | "control">("timing");
  const drivers = Object.values(state.drivers).sort((a, b) => (a.position ?? 999) - (b.position ?? 999));
  return <><SessionSplit className="session-layout practice-layout session-desktop" timingWidth={timingWidth} onTimingWidthChange={onTimingWidthChange} timing={<TimingTower drivers={drivers} variant="practice" analytics={analytics} replayAvailable={replayAvailable} onSelectDriver={onSelectDriver} />} analysis={<div className="analysis-stack">
      <TrackMap circuit={state.circuit} session={state.session} drivers={drivers} positionMode={positionMode} viewingMode={viewingMode} />
      <Conditions weather={state.weather} session={state.session} />
      {story && <div className="session-story">{story}</div>}
      <RaceControl messages={state.race_control} />
    </div>} /><div className="mobile-session mobile-practice-session"><nav className="mobile-priority-tabs" aria-label="Practice views">{(["timing", "runs", "track", "control"] as const).map((tab) => <button className={mobileTab === tab ? "active" : ""} key={tab} onClick={() => setMobileTab(tab)}>{({ timing: "TIMING", runs: "RUNS", track: "TRACK", control: "ACTIVITY" })[tab]}</button>)}</nav><div className="mobile-session-content"><div className="mobile-primary">{mobileTab === "timing" ? <PhoneTimingTower drivers={drivers} variant="practice" analytics={analytics} replayAvailable={replayAvailable} onSelectDriver={onSelectDriver} /> : mobileTab === "runs" ? <div className="phone-runs"><header><strong>CURRENT RUNS</strong><span>Open a driver for stint and pit history</span></header>{drivers.map((driver) => <button key={driver.number} onClick={() => onSelectDriver(driver.number)}><strong>{driver.code ?? driver.number}</strong><span>{driver.team ?? "—"}</span><b>{driver.stint_laps == null ? "—" : `${driver.stint_laps}L`}</b><small>{driver.pit_count} PIT</small></button>)}</div> : mobileTab === "track" ? <div className="mobile-map-stack"><TrackMap circuit={state.circuit} session={state.session} drivers={drivers} positionMode={positionMode} viewingMode={viewingMode} /><Conditions weather={state.weather} session={state.session} /></div> : <div className="phone-activity">{story}<RaceControl messages={state.race_control} /></div>}</div><div className="landscape-companion">{mobileTab === "timing" ? <TrackMap circuit={state.circuit} session={state.session} drivers={drivers} positionMode={positionMode} viewingMode={viewingMode} /> : <PhoneTimingTower drivers={drivers} variant="practice" analytics={analytics} replayAvailable={replayAvailable} onSelectDriver={onSelectDriver} />}</div></div></div></>;
}
