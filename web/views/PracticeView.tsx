import { useState } from "react";

import { Conditions } from "../components/analysis/Conditions";
import { RaceControl } from "../components/analysis/RaceControl";
import { TrackMap } from "../components/analysis/TrackMap";
import { TimingTower } from "../components/timing/TimingTower";
import type { PositionMode, ViewingMode, RaceState } from "../domain/protocol";

export function PracticeView({ state, replayAvailable, positionMode, viewingMode, onSelectDriver }: { state: RaceState; replayAvailable: boolean; positionMode: PositionMode; viewingMode: ViewingMode; onSelectDriver: (driverNumber: string) => void }) {
  const [mobileTab, setMobileTab] = useState<"timing" | "track" | "conditions" | "control">("timing");
  const drivers = Object.values(state.drivers).sort((a, b) => (a.position ?? 999) - (b.position ?? 999));
  return <><div className="session-layout practice-layout session-desktop">
    <TimingTower drivers={drivers} variant="practice" replayAvailable={replayAvailable} onSelectDriver={onSelectDriver} />
    <div className="analysis-stack">
      <TrackMap circuit={state.circuit} session={state.session} drivers={drivers} positionMode={positionMode} viewingMode={viewingMode} />
      <Conditions weather={state.weather} session={state.session} />
      <RaceControl messages={state.race_control} />
    </div>
  </div><div className="mobile-session mobile-practice-session"><nav className="mobile-priority-tabs">{(["timing", "track", "conditions", "control"] as const).map((tab) => <button className={mobileTab === tab ? "active" : ""} key={tab} onClick={() => setMobileTab(tab)}>{tab.toUpperCase()}</button>)}</nav><div className="mobile-session-content">{mobileTab === "timing" ? <TimingTower drivers={drivers} variant="practice" replayAvailable={replayAvailable} onSelectDriver={onSelectDriver} /> : mobileTab === "track" ? <TrackMap circuit={state.circuit} session={state.session} drivers={drivers} positionMode={positionMode} viewingMode={viewingMode} /> : mobileTab === "conditions" ? <Conditions weather={state.weather} session={state.session} /> : <RaceControl messages={state.race_control} />}</div></div></>;
}
