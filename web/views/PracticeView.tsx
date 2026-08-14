import { Conditions } from "../components/analysis/Conditions";
import { RaceControl } from "../components/analysis/RaceControl";
import { TrackMap } from "../components/analysis/TrackMap";
import { Panel } from "../components/shared/Panel";
import { TimingTower } from "../components/timing/TimingTower";
import type { PositionMode, RaceState } from "../domain/protocol";

export function PracticeView({ state, replayAvailable, positionMode, onSelectDriver }: { state: RaceState; replayAvailable: boolean; positionMode: PositionMode; onSelectDriver: (driverNumber: string) => void }) {
  const [mobileTab, setMobileTab] = useState<"timing" | "runs" | "pace" | "stints">("timing");
  const drivers = Object.values(state.drivers).sort((a, b) => (a.position ?? 999) - (b.position ?? 999));
  const analysis = <Panel eyebrow="ANALYTICS" title="Run analysis"><div className="unknown-block"><strong>ANALYTICS - NOT ENABLED</strong><p>Normalized lap evidence is retained for the later tested analytics milestone. No calculated metric is shown yet.</p></div></Panel>;
  return <><div className="session-layout practice-layout session-desktop">
    <TimingTower drivers={drivers} variant="practice" replayAvailable={replayAvailable} onSelectDriver={onSelectDriver} />
    <div className="analysis-stack">
      {analysis}
      <TrackMap circuit={state.circuit} session={state.session} drivers={drivers} positionMode={positionMode} />
      <Conditions weather={state.weather} session={state.session} />
      <RaceControl messages={state.race_control} />
    </div>
  </div><div className="mobile-session mobile-practice-session"><nav className="mobile-priority-tabs">{(["timing", "runs", "pace", "stints"] as const).map((tab) => <button className={mobileTab === tab ? "active" : ""} key={tab} onClick={() => setMobileTab(tab)}>{tab.toUpperCase()}</button>)}</nav><div className="mobile-session-content">{mobileTab === "timing" ? <TimingTower drivers={drivers} variant="practice" replayAvailable={replayAvailable} onSelectDriver={onSelectDriver} /> : <Panel eyebrow={mobileTab === "runs" ? "RUNS" : mobileTab === "pace" ? "PACE" : "STINTS"} title={mobileTab === "runs" ? "Run context" : mobileTab === "pace" ? "Pace context" : "Stint history"}><div className="unknown-block"><strong>ANALYTICS - NOT ENABLED</strong><p>Factual timing remains available. No derived practice model is invented.</p></div></Panel>}</div></div></>;
}
import { useState } from "react";
