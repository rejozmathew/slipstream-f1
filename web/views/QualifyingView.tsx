import { Conditions } from "../components/analysis/Conditions";
import { RaceControl } from "../components/analysis/RaceControl";
import { TrackMap } from "../components/analysis/TrackMap";
import { Panel } from "../components/shared/Panel";
import { TimingTower } from "../components/timing/TimingTower";
import type { PositionMode, RaceState } from "../domain/protocol";

export function QualifyingView({ state, replayAvailable, positionMode }: { state: RaceState; replayAvailable: boolean; positionMode: PositionMode }) {
  const drivers = Object.values(state.drivers).sort((a, b) => (a.position ?? 999) - (b.position ?? 999));
  return <div className="session-layout qualifying-layout">
    <TimingTower drivers={drivers} variant="qualifying" replayAvailable={replayAvailable} />
    <div className="analysis-stack">
      <Panel eyebrow="SESSION CONTEXT" title="Qualifying phase"><div className="unknown-block"><strong>PHASE - UNKNOWN</strong><p>The current normalized feed does not expose a canonical Q1/Q2/Q3 phase. No cut line is invented.</p></div></Panel>
      <TrackMap circuit={state.circuit} session={state.session} drivers={drivers} positionMode={positionMode} />
      <Conditions weather={state.weather} session={state.session} />
      <RaceControl messages={state.race_control} />
    </div>
  </div>;
}
