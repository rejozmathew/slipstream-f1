import { useState } from "react";

import { Conditions } from "../components/analysis/Conditions";
import { RaceControl } from "../components/analysis/RaceControl";
import { TrackMap } from "../components/analysis/TrackMap";
import { Panel } from "../components/shared/Panel";
import { TimingTower } from "../components/timing/TimingTower";
import type { AnalyticsSnapshot, PositionMode, QualifyingIntelligence, RaceState, SessionKind } from "../domain/protocol";

function SessionPanel({ intelligence }: { intelligence: QualifyingIntelligence | null }) {
  const phaseKnown = intelligence?.phase && intelligence.phase !== "UNKNOWN";
  const showAdvance = phaseKnown && !["Q3", "SQ3"].includes(intelligence.phase);
  return <Panel eyebrow="QUALIFYING" title="SESSION" className="qualifying-session-panel">
    <div className="qualifying-session-grid">
      {phaseKnown && <div><span>SEGMENT</span><strong>{intelligence.phase}</strong></div>}
      {phaseKnown && intelligence.sessionClock && <div><span>TIME LEFT</span><strong>{intelligence.sessionClock}</strong></div>}
      {intelligence?.benchmark && <div><span>FASTEST</span><strong>{intelligence.benchmark.code ?? intelligence.benchmark.driverNumber} {intelligence.benchmark.lapTime}</strong></div>}
      {showAdvance && intelligence.cutLine.advancePosition && <div><span>ADVANCE</span><strong>TOP {intelligence.cutLine.advancePosition}</strong></div>}
    </div>
    {intelligence?.phase === "UNKNOWN" && <p className="qualifying-evidence-note">SEGMENT TIMING WAS NOT RECORDED FOR THIS REPLAY</p>}
  </Panel>;
}

export function QualifyingView({ state, analytics, replayAvailable, positionMode, sectorTimingAvailable, onSelectDriver }: { state: RaceState; analytics: AnalyticsSnapshot | null; sessionKind: SessionKind; replayAvailable: boolean; positionMode: PositionMode; sectorTimingAvailable: boolean; onSelectDriver: (driverNumber: string) => void }) {
  const [mobileTab, setMobileTab] = useState<"timing" | "session" | "track" | "conditions" | "control">("timing");
  const drivers = Object.values(state.drivers).sort((a, b) => (a.position ?? 999) - (b.position ?? 999));
  const intelligence = analytics?.qualifying?.status === "AVAILABLE" ? analytics.qualifying : null;
  const session = <SessionPanel intelligence={intelligence} />;
  const tabs = ["timing", "session", "track", "conditions", "control"] as const;
  return <><div className="session-layout qualifying-layout session-desktop">
    <TimingTower drivers={drivers} variant="qualifying" analytics={analytics} replayAvailable={replayAvailable} sectorTimingAvailable={sectorTimingAvailable} onSelectDriver={onSelectDriver} />
    <div className="analysis-stack">
      {session}
      <TrackMap circuit={state.circuit} session={state.session} drivers={drivers} positionMode={positionMode} />
      <Conditions weather={state.weather} session={state.session} />
      <RaceControl messages={state.race_control} />
    </div>
  </div><div className="mobile-session mobile-qualifying-session"><nav className="mobile-priority-tabs" style={{ gridTemplateColumns: `repeat(${tabs.length}, 1fr)` }}>{tabs.map((tab) => <button className={mobileTab === tab ? "active" : ""} key={tab} onClick={() => setMobileTab(tab)}>{tab.toUpperCase()}</button>)}</nav><div className="mobile-session-content">{mobileTab === "timing" ? <TimingTower drivers={drivers} variant="qualifying" analytics={analytics} replayAvailable={replayAvailable} sectorTimingAvailable={sectorTimingAvailable} onSelectDriver={onSelectDriver} /> : mobileTab === "session" ? session : mobileTab === "track" ? <TrackMap circuit={state.circuit} session={state.session} drivers={drivers} positionMode={positionMode} /> : mobileTab === "conditions" ? <Conditions weather={state.weather} session={state.session} /> : <RaceControl messages={state.race_control} />}</div></div></>;
}
