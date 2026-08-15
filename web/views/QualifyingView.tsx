import { useState } from "react";

import { Conditions } from "../components/analysis/Conditions";
import { RaceControl } from "../components/analysis/RaceControl";
import { TrackMap } from "../components/analysis/TrackMap";
import { Panel } from "../components/shared/Panel";
import { TimingTower } from "../components/timing/TimingTower";
import type { PositionMode, RaceState, SessionKind } from "../domain/protocol";

export function QualifyingView({ state, sessionKind, replayAvailable, positionMode, onSelectDriver }: { state: RaceState; sessionKind: SessionKind; replayAvailable: boolean; positionMode: PositionMode; onSelectDriver: (driverNumber: string) => void }) {
  const [mobileTab, setMobileTab] = useState<"timing" | "cutline" | "runs" | "sectors">("timing");
  const drivers = Object.values(state.drivers).sort((a, b) => (a.position ?? 999) - (b.position ?? 999));
  const sprintQualifying = sessionKind === "sprint_qualifying";
  const phase = <Panel eyebrow="SESSION CONTEXT" title={sprintQualifying ? "Sprint Qualifying phase" : "Qualifying phase"}><div className="unknown-block"><strong>{sprintQualifying ? "SQ PHASE" : "Q PHASE"} - UNKNOWN</strong><p>The current normalized feed does not expose a canonical {sprintQualifying ? "SQ1/SQ2/SQ3" : "Q1/Q2/Q3"} phase. No cut line is invented.</p></div></Panel>;
  return <><div className="session-layout qualifying-layout session-desktop">
    <TimingTower drivers={drivers} variant="qualifying" replayAvailable={replayAvailable} onSelectDriver={onSelectDriver} />
    <div className="analysis-stack">
      {phase}
      <TrackMap circuit={state.circuit} session={state.session} drivers={drivers} positionMode={positionMode} />
      <Conditions weather={state.weather} session={state.session} />
      <RaceControl messages={state.race_control} />
    </div>
  </div><div className="mobile-session mobile-qualifying-session"><nav className="mobile-priority-tabs">{(["timing", "cutline", "runs", "sectors"] as const).map((tab) => <button className={mobileTab === tab ? "active" : ""} key={tab} onClick={() => setMobileTab(tab)}>{tab.toUpperCase()}</button>)}</nav><div className="mobile-session-content">{mobileTab === "timing" ? <TimingTower drivers={drivers} variant="qualifying" replayAvailable={replayAvailable} onSelectDriver={onSelectDriver} /> : mobileTab === "cutline" ? phase : mobileTab === "sectors" ? <Panel eyebrow="SECTOR EVIDENCE" title="Sector status"><div className="unknown-block"><strong>MINISECTORS - NOT AVAILABLE</strong><p>Current factual sector values remain visible in Timing. Precise minisectors are not in this source contract.</p></div></Panel> : <Panel eyebrow="RUNS" title="Run context"><div className="unknown-block"><strong>RUN ANALYTICS - NOT ENABLED</strong><p>No qualifying run model is substituted.</p></div></Panel>}</div></div></>;
}
